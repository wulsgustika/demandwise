"""Prediksi permintaan: jalankan, baca, evaluasi, latih ulang, koreksi pemilik."""
import re
import time

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from . import _db, _integrasi, data_akses as da, k, musiman
from ._util import aksi_aman, df_aman, hari_ini, hasil, log
from .model_prediksi import NAMA_MA, NAMA_RF, proses_produk

KOLOM_PREDIKSI = ["produk_id", "nama_produk", "tanggal", "qty_aktual", "qty_prediksi", "tipe"]
KOLOM_EVALUASI = ["produk_id", "nama_produk", "model", "versi", "mae", "rmse", "mape",
                  "dievaluasi_pada", "dipakai"]
_sudah_coba_otomatis = False


def _param() -> dict:
    return dict(rf_pohon=k.RF_JUMLAH_POHON, rf_daun=k.RF_MIN_SAMPEL_DAUN, ma_window=k.MA_WINDOW_HARI,
                rf_min_hari=k.RF_MIN_HARI_DATA, bt_horizon=k.BACKTEST_HORIZON_HARI,
                bt_fold=k.BACKTEST_JUMLAH_FOLD, bt_fold_event=2, kriteria=k.KRITERIA_PILIH_MODEL,
                bobot_koreksi=k.BOBOT_KOREKSI_PEMILIK)


def _versi_berikut() -> str:
    df = _db.baca("SELECT DISTINCT versi FROM evaluasi_model")
    nomor = [int(m.group(1)) for v in df["versi"].dropna() if (m := re.fullmatch(r"v(\d+)", str(v)))]
    return f"v{(max(nomor) if nomor else 0) + 1}"


def _ringkas_mape(metrik_df: pd.DataFrame, model_dipakai: dict) -> dict:
    """Rata-rata & median MAPE dari model yang dipakai tiap produk."""
    dipakai = metrik_df[[model_dipakai.get(r.produk_id) == r.model for r in metrik_df.itertuples()]]
    v = dipakai["mape"].dropna()
    return {"mape_rata2": float(v.mean()) if len(v) else None,
            "mape_median": float(v.median()) if len(v) else None,
            "mae_rata2": float(dipakai["mae"].dropna().mean()) if len(dipakai) else None}


def _pipeline(horizon_hari: int, progress=None) -> dict:
    t0 = time.time()
    horizon = max(int(horizon_hari), int(k.HORIZON_MINIMAL_HARI))
    pv, tutup = da.penjualan_harian_matriks()
    if pv.empty:
        return hasil(False, "Belum ada data penjualan untuk dilatih")
    h = hari_ini()
    musiman.pastikan_event_otomatis(h, pv.index)
    events = da.events_list()
    prod = da.produk_aktif()
    prod = prod[prod["produk_id"].isin(pv.columns)]
    if prod.empty:
        return hasil(False, "Tidak ada produk aktif yang punya riwayat penjualan")
    kor = da.koreksi_terbaru()
    kor_map = {}
    for r in kor.itertuples():
        kor_map.setdefault(int(r.produk_id), {})[pd.Timestamp(r.tanggal_target)] = float(r.qty_koreksi)

    mulai = pv.index[-1] + pd.Timedelta(days=1)
    n_langkah = horizon + max(0, (h - mulai).days)
    param = _param()
    ids = [int(x) for x in prod["produk_id"]]
    nama = dict(zip(prod["produk_id"], prod["nama_produk"]))

    if k.N_JOBS == 1:
        hasil_produk = []
        for i, pid in enumerate(ids, 1):
            hasil_produk.append(proses_produk(pid, pv[pid], tutup, events, n_langkah, kor_map.get(pid, {}), param))
            if progress:
                progress(i, len(ids), nama[pid])
    else:
        hasil_produk = Parallel(n_jobs=k.N_JOBS)(
            delayed(proses_produk)(pid, pv[pid], tutup, events, n_langkah, kor_map.get(pid, {}), param) for pid in ids)
        if progress:
            progress(len(ids), len(ids), "selesai")

    # --- simpan prediksi (ganti semua baris dengan tanggal_target >= tanggal mulai) ---
    sekarang = _db.sekarang()
    baris = []
    for r in hasil_produk:
        for tgl, q in zip(r["tanggal"], r["prediksi"]):
            baris.append({"produk_id": r["produk_id"], "tanggal_target": tgl.date(),
                          "qty_prediksi": round(float(q), 3), "model": r["model"], "dibuat_pada": sekarang})
    with _db.get_engine().begin() as conn:
        conn.execute(_db.T_HASIL_PREDIKSI.delete().where(_db.T_HASIL_PREDIKSI.c.tanggal_target >= mulai.date()))
        conn.execute(_db.T_HASIL_PREDIKSI.insert(), baris)

    # --- simpan evaluasi ---
    versi = _versi_berikut()
    ev_baris = []
    for r in hasil_produk:
        for m in r["metrik"]:
            ev_baris.append({"produk_id": r["produk_id"], "model": m["model"], "versi": versi,
                             "mae": None if pd.isna(m["mae"]) else round(m["mae"], 4),
                             "rmse": None if pd.isna(m["rmse"]) else round(m["rmse"], 4),
                             "mape": None if pd.isna(m["mape"]) else round(m["mape"], 2),
                             "dievaluasi_pada": sekarang})
    _db.sisip(_db.T_EVALUASI, ev_baris)
    model_dipakai = {r["produk_id"]: r["model"] for r in hasil_produk}
    ringkas = _ringkas_mape(pd.DataFrame(ev_baris), model_dipakai)

    # --- indeks musim, peringatan, rekomendasi ---
    musiman.hitung_indeks_musim(pv, tutup)
    from . import peringatan  # impor lambat: hindari impor melingkar
    notif = peringatan.jalankan_semua(h)

    hitung = pd.Series(model_dipakai).value_counts().to_dict()
    return hasil(True, f"Prediksi {len(ids)} produk selesai ({versi})", {
        "versi": versi, "jumlah_produk": len(ids), "horizon_hari": horizon,
        "tanggal_mulai": str(mulai.date()), "tanggal_akhir": str(idx_akhir(hasil_produk)),
        "model_dipakai": {NAMA_RF: int(hitung.get(NAMA_RF, 0)), NAMA_MA: int(hitung.get(NAMA_MA, 0))},
        **ringkas, "notifikasi_baru": notif, "durasi_detik": round(time.time() - t0, 1)})


def idx_akhir(hasil_produk):
    return max(r["tanggal"][-1] for r in hasil_produk).date()


@aksi_aman
def jalankan_prediksi(horizon_hari=30, progress=None) -> dict:
    """Latih & prediksi semua produk aktif. `progress(i, total, nama)` opsional untuk progress bar."""
    global _sudah_coba_otomatis
    _sudah_coba_otomatis = True
    return _pipeline(horizon_hari, progress)


def pastikan_prediksi():
    """Kalau hasil_prediksi kosong/basi, jalankan sekali per proses (supaya halaman tidak kosong)."""
    global _sudah_coba_otomatis
    if _sudah_coba_otomatis:
        return
    df = _db.baca("SELECT MAX(tanggal_target) AS t FROM hasil_prediksi", tanggal=["t"])
    t = df["t"].iloc[0]
    if pd.isna(t) or pd.Timestamp(t) < hari_ini() + pd.Timedelta(days=7):
        _sudah_coba_otomatis = True
        r = _pipeline(k.HORIZON_MINIMAL_HARI)
        if not r["ok"]:
            log.warning("Prediksi otomatis gagal: %s", r["pesan"])


def prediksi_matriks(mulai, n: int, pv: pd.DataFrame = None, tutup=None) -> pd.DataFrame:
    """Prediksi per produk aktif: baris = produk_id, kolom = n tanggal mulai `mulai`.
    Tanggal di luar horizon diisi rata-rata prediksi produk itu; produk tanpa prediksi -> rata-rata 14 hari terakhir."""
    pastikan_prediksi()
    mulai = pd.Timestamp(mulai)
    tgl = pd.date_range(mulai, periods=n, freq="D")
    prod_ids = da.produk_aktif()["produk_id"].tolist()
    pred = da.prediksi_tersimpan()
    if pred.empty:
        wide = pd.DataFrame(index=prod_ids, columns=tgl, dtype=float)
    else:
        wide = pred.pivot(index="produk_id", columns="tanggal", values="qty_prediksi")
        wide = wide.reindex(index=prod_ids, columns=tgl)
    rata = wide.mean(axis=1)
    if rata.isna().any():
        if pv is None:
            pv, tutup = da.penjualan_harian_matriks()
        buka = pv.loc[~pv.index.isin(tutup)].tail(14)
        for pid in rata[rata.isna()].index:
            rata[pid] = float(buka[pid].mean()) if pid in buka.columns else 0.0
    for c in wide.columns:
        wide[c] = wide[c].fillna(rata)
    wide.index.name = "produk_id"
    return wide


# ---------------------------------------------------------------------------
# Baca hasil
# ---------------------------------------------------------------------------
@df_aman(KOLOM_PREDIKSI)
def get_prediksi(produk_id, horizon_hari=30) -> pd.DataFrame:
    """Riwayat penjualan (tipe 'historis') + prediksi ke depan (tipe 'prediksi').
    Koreksi pemilik sudah diterapkan pada qty_prediksi. produk_id=None -> semua produk."""
    pastikan_prediksi()
    pv, tutup = da.penjualan_harian_matriks()
    prod = da.semua_produk().set_index("produk_id")["nama_produk"]
    ids = [int(produk_id)] if produk_id is not None else da.produk_aktif()["produk_id"].tolist()
    pred = da.prediksi_tersimpan()
    h = hari_ini()
    terakhir = pv.index[-1]
    potong_hist = terakhir - pd.Timedelta(days=int(k.HISTORIS_TAMPIL_HARI) - 1)
    akhir_pred = h + pd.Timedelta(days=int(horizon_hari) - 1)
    bagian = []
    for pid in ids:
        if pid in pv.columns:
            hist = pv[pid].loc[potong_hist:].copy()
            hist[hist.index.isin(tutup)] = np.nan
            dh = pd.DataFrame({"tanggal": hist.index, "qty_aktual": hist.values})
        else:
            dh = pd.DataFrame(columns=["tanggal", "qty_aktual"])
        pp = pred[pred["produk_id"] == pid][["tanggal", "qty_prediksi"]]
        dh = dh.merge(pp, on="tanggal", how="left")
        dh["tipe"] = "historis"
        depan = pp[(pp["tanggal"] > terakhir) & (pp["tanggal"] <= akhir_pred)].copy()
        depan["qty_aktual"] = np.nan
        depan["tipe"] = "prediksi"
        gab = pd.concat([dh, depan], ignore_index=True)
        gab["produk_id"] = pid
        gab["nama_produk"] = prod.get(pid)
        bagian.append(gab)
    if not bagian:
        return pd.DataFrame(columns=KOLOM_PREDIKSI)
    df = pd.concat(bagian, ignore_index=True)
    df["qty_prediksi"] = df["qty_prediksi"].astype(float).round(2)
    return df[KOLOM_PREDIKSI].sort_values(["produk_id", "tanggal"]).reset_index(drop=True)


@df_aman(KOLOM_EVALUASI)
def get_evaluasi_model(semua_versi=False) -> pd.DataFrame:
    """Evaluasi model per produk. Default hanya versi terbaru; semua_versi=True untuk riwayat."""
    ev = _db.baca("SELECT id, produk_id, model, versi, mae, rmse, mape, dievaluasi_pada FROM evaluasi_model",
                  tanggal=["dievaluasi_pada"])
    if ev.empty:
        return pd.DataFrame(columns=KOLOM_EVALUASI)
    if not semua_versi:
        ev = ev[ev["versi"] == ev.loc[ev["id"].idxmax(), "versi"]]
    prod = da.semua_produk()
    pred = da.prediksi_tersimpan(terapkan_koreksi=False)
    pakai = pred.groupby("produk_id")["model"].last() if not pred.empty else pd.Series(dtype=object)
    ev = ev.merge(prod, on="produk_id", how="left")
    ev["dipakai"] = [pakai.get(r.produk_id) == r.model for r in ev.itertuples()]
    return ev[KOLOM_EVALUASI].sort_values(["versi", "produk_id", "model"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Koreksi pemilik & latih ulang
# ---------------------------------------------------------------------------
@aksi_aman
def simpan_koreksi(produk_id, tanggal_target, qty_koreksi, alasan) -> dict:
    prod = da.semua_produk()
    if int(produk_id) not in set(prod["produk_id"]):
        return hasil(False, "Produk tidak ditemukan")
    try:
        q = float(qty_koreksi)
    except (TypeError, ValueError):
        return hasil(False, "Jumlah koreksi harus berupa angka")
    if q < 0:
        return hasil(False, "Jumlah koreksi tidak boleh negatif")
    try:
        tgl = pd.Timestamp(tanggal_target).normalize()
    except Exception:
        return hasil(False, "Format tanggal tidak valid (gunakan YYYY-MM-DD)")
    if pd.isna(tgl):
        return hasil(False, "Format tanggal tidak valid (gunakan YYYY-MM-DD)")
    _db.sisip(_db.T_KOREKSI, [{"produk_id": int(produk_id), "tanggal_target": tgl.date(),
                               "qty_koreksi": q, "alasan": (alasan or "").strip() or None,
                               "dibuat_pada": _db.sekarang()}])
    return hasil(True, "Koreksi tersimpan. Langsung dipakai pada tampilan prediksi dan dipelajari saat latih ulang.",
                 {"produk_id": int(produk_id), "tanggal_target": str(tgl.date()), "qty_koreksi": q})


def _evaluasi_realisasi(h) -> dict:
    """Bandingkan prediksi tersimpan (tanggal < hari ini) dengan penjualan sebenarnya."""
    pred = da.prediksi_tersimpan(terapkan_koreksi=False)
    kosong = {"hari_dibandingkan": 0, "mape": None, "mae": None, "koreksi_lebih_baik": 0, "koreksi_dinilai": 0}
    if pred.empty:
        return kosong
    pv, tutup = da.penjualan_harian_matriks()
    pred = pred[(pred["tanggal"] < h) & (pred["tanggal"].isin(pv.index)) & (~pred["tanggal"].isin(tutup))]
    if pred.empty:
        return kosong
    pred = pred.copy()
    pred["aktual"] = [pv.at[r.tanggal, r.produk_id] if r.produk_id in pv.columns else np.nan
                      for r in pred.itertuples()]
    pred = pred.dropna(subset=["aktual"])
    from .model_prediksi import metrik
    m = metrik(pred["aktual"], pred["qty_prediksi"])
    out = {**kosong, "hari_dibandingkan": int(len(pred)), "mape": m["mape"], "mae": m["mae"]}
    kor = da.koreksi_terbaru()
    if not kor.empty:
        j = kor.merge(pred, left_on=["produk_id", "tanggal_target"], right_on=["produk_id", "tanggal"])
        if not j.empty:
            out["koreksi_dinilai"] = int(len(j))
            out["koreksi_lebih_baik"] = int((abs(j["qty_koreksi"] - j["aktual"]) < abs(j["qty_prediksi"] - j["aktual"])).sum())
    return out


def _koma(x, nd=1):
    return f"{x:.{nd}f}".replace(".", ",")


@aksi_aman
def evaluasi_dan_retrain(progress=None) -> dict:
    """1) nilai prediksi lama vs realisasi, 2) latih ulang semua model dengan data + koreksi terbaru,
    3) simpan evaluasi versi baru, 4) kirim notifikasi model_diperbarui."""
    global _sudah_coba_otomatis
    _sudah_coba_otomatis = True
    h = hari_ini()
    lama = _db.baca("SELECT id, versi FROM evaluasi_model ORDER BY id DESC LIMIT 1")
    versi_lama = lama["versi"].iloc[0] if len(lama) else None
    mape_lama = None
    if versi_lama:
        ev = get_evaluasi_model(semua_versi=True)
        ev = ev[(ev["versi"] == versi_lama) & ev["dipakai"]]
        mape_lama = float(ev["mape"].mean()) if ev["mape"].notna().any() else None
    realisasi = _evaluasi_realisasi(h)
    r = _pipeline(k.HORIZON_MINIMAL_HARI, progress)
    if not r["ok"]:
        return r
    d = r["data"]
    d.update({"versi_sebelumnya": versi_lama, "mape_versi_sebelumnya": mape_lama, "realisasi": realisasi})
    mape = d.get("mape_rata2")
    if mape is not None:
        pesan = f"Latih ulang selesai ({d['versi']}). MAPE rata-rata model terpilih {_koma(mape)}%"
        pesan += f" (sebelumnya {_koma(mape_lama)}%)." if mape_lama is not None else "."
    else:
        pesan = f"Latih ulang selesai ({d['versi']}). MAPE belum bisa dihitung (data terlalu sedikit)."
    if realisasi["mape"] is not None:
        pesan += f" Prediksi lama vs realisasi: MAPE {_koma(realisasi['mape'])}% pada {realisasi['hari_dibandingkan']} data produk-hari."
    _integrasi.kirim("model_diperbarui", "info", f"Model diperbarui ({d['versi']})", pesan, dedupe=None)
    return hasil(True, pesan, d)
