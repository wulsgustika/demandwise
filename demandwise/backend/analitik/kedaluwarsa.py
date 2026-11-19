"""Risiko kedaluwarsa per batch + rekomendasi tindakan (diskon / bundling / retur)."""
import math

import numpy as np
import pandas as pd

from . import _db, data_akses as da, k
from ._util import aksi_aman, df_aman, hari_ini, hasil, rp, tgl_id
from .prediksi import prediksi_matriks

KOLOM_RISIKO = ["batch_id", "produk_id", "nama_produk", "tgl_kedaluwarsa", "sisa_hari", "stok_batch",
                "prediksi_harian", "proyeksi_laku", "jumlah_berisiko", "level", "rekomendasi"]
KOLOM_TINDAKAN = ["id", "batch_id", "produk_id", "nama_produk", "tgl_kedaluwarsa", "sisa_hari",
                  "stok_batch", "jumlah_berisiko", "level", "jenis", "detail", "harga_diskon",
                  "hpp_satuan", "harga_jual", "status", "dibuat_pada"]
URUT_LEVEL = {"kritis": 0, "siaga": 1, "waspada": 2, "aman": 3}


def tentukan_level(sisa_hari: float, jumlah_berisiko: float) -> str:
    """H-30 waspada, H-14 siaga, H-7 kritis (mode "risiko": hanya kalau ada jumlah berisiko)."""
    if k.LEVEL_MODE == "risiko" and jumlah_berisiko < 1:
        return "aman"
    if sisa_hari < 0:
        return "kritis"
    if sisa_hari <= k.LEVEL_KRITIS_HARI:
        return "kritis"
    if sisa_hari <= k.LEVEL_SIAGA_HARI:
        return "siaga"
    if sisa_hari <= k.LEVEL_WASPADA_HARI:
        return "waspada"
    return "aman"


def harga_diskon(harga_jual, persen, hpp) -> int:
    """Diskon `persen` dari harga jual, dibulatkan ke atas per Rp100, TIDAK di bawah HPP batch."""
    target = math.ceil(float(harga_jual) * (1 - persen / 100.0) / 100.0) * 100
    return int(min(float(harga_jual), max(target, math.ceil(float(hpp)))))


def rencana_tindakan(level, sisa_hari, stok_batch, berisiko, hpp, harga_jual, pemasok, partner):
    """Return (jenis, detail, harga_diskon). Satu rekomendasi utama per batch."""
    if sisa_hari < 0:
        return ("lainnya", f"Batch sudah lewat kedaluwarsa ({tgl_id_hari(sisa_hari)}). "
                "Tarik dari rak jual dan catat write-off.", None)
    persen = k.DISKON_PERSEN[level]
    hd = harga_diskon(harga_jual, persen, hpp)
    batas = f"harga {rp(hd)} (diskon {persen}%, tidak di bawah HPP {rp(hpp)})"
    if berisiko < 1:  # level waktu sudah masuk H-30/H-14/H-7, tapi prediksi menunjukkan stok habis terjual
        return ("diskon", "Diperkirakan habis terjual sebelum kedaluwarsa, tindakan bersifat pencegahan. "
                f"Opsi: diskon bertahap {batas} dan pindahkan ke rak depan.", hd)
    if (level == "kritis" and pemasok and stok_batch > 0 and sisa_hari >= k.RETUR_MIN_SISA_HARI
            and berisiko / stok_batch >= k.RETUR_MIN_PROPORSI_RISIKO):
        return ("retur_pemasok", f"Ajukan retur sekitar {int(berisiko)} unit ke {pemasok}; sisanya jual dengan {batas} "
                "dan pindahkan ke rak depan.", hd)
    if level in ("siaga", "kritis") and partner:
        return ("bundling", f"Bundling dengan {partner} (fast-moving), {batas}. Pindahkan ke rak depan.", hd)
    return ("diskon", f"Diskon bertahap: {batas}. Pindahkan ke rak depan.", hd)


def tgl_id_hari(sisa_hari):
    return f"lewat {abs(int(sisa_hari))} hari"


def _partner_bundling(pid, kategori_id, kec: pd.DataFrame, stok: pd.Series):
    """Produk fast-moving yang stoknya ada; utamakan kategori yang sama."""
    c = kec[(kec["kecepatan"] == "fast") & (kec["produk_id"] != pid) & (kec["produk_id"].map(stok).fillna(0) > 0)]
    if c.empty:
        return None
    sama = c[c["kategori_id"] == kategori_id]
    pilih = (sama if not sama.empty else c).sort_values("qty_per_hari", ascending=False)
    return pilih["nama_produk"].iloc[0]


def hitung_risiko(h=None) -> pd.DataFrame:
    """Semua batch aktif + level risiko. Kolom tambahan internal: hpp_satuan, harga_jual, jenis_tindakan, harga_diskon."""
    from .profit import tabel_kecepatan
    h = h if h is not None else hari_ini()
    b = da.batch_aktif()
    if b.empty:
        return pd.DataFrame(columns=KOLOM_RISIKO + ["hpp_satuan", "harga_jual", "jenis_tindakan", "harga_diskon", "kategori_id"])
    prod = da.produk_aktif().set_index("produk_id")
    b = b[b["produk_id"].isin(prod.index)].copy()
    pv, tutup = da.penjualan_harian_matriks()
    n_pred = int(max(k.OVERSTOCK_HORIZON_HARI, 30))
    pred = prediksi_matriks(h, n_pred, pv, tutup)
    kec = tabel_kecepatan(pv, tutup, h)
    stok = b[b["tgl_kedaluwarsa"] >= h].groupby("produk_id")["jumlah_sisa"].sum()
    baris = []
    for r in b.itertuples():
        pr = pred.loc[r.produk_id].to_numpy()
        sisa = int((r.tgl_kedaluwarsa - h).days)
        jendela = int(min(max(sisa, 1), len(pr)))
        harian = float(pr[:jendela].mean())
        proyeksi = min(float(r.jumlah_sisa), harian * max(sisa, 0))
        berisiko = max(0.0, float(r.jumlah_sisa) - harian * max(sisa, 0))     # rumus KONTRAK
        berisiko_i = int(round(berisiko))
        level = tentukan_level(sisa, berisiko_i)
        p = prod.loc[r.produk_id]
        jenis, detail, hd = (None, "Tidak perlu tindakan", None)
        if sisa < 0:
            berisiko_i = int(r.jumlah_sisa)                      # sudah lewat tanggal: seluruh stok
            jenis, detail, hd = rencana_tindakan("kritis", sisa, r.jumlah_sisa, berisiko_i, r.hpp_satuan,
                                                 p["harga_jual"], p["pemasok"], None)
        elif level != "aman":
            partner = _partner_bundling(r.produk_id, p["kategori_id"], kec, stok)
            jenis, detail, hd = rencana_tindakan(level, sisa, r.jumlah_sisa, berisiko_i, r.hpp_satuan,
                                                 p["harga_jual"], p["pemasok"], partner)
        baris.append({"batch_id": r.batch_id, "produk_id": r.produk_id, "nama_produk": p["nama_produk"],
                      "tgl_kedaluwarsa": r.tgl_kedaluwarsa, "sisa_hari": sisa, "stok_batch": int(r.jumlah_sisa),
                      "prediksi_harian": round(harian, 2), "proyeksi_laku": round(proyeksi, 1),
                      "jumlah_berisiko": berisiko_i, "level": level, "rekomendasi": detail,
                      "hpp_satuan": r.hpp_satuan, "harga_jual": p["harga_jual"],
                      "jenis_tindakan": jenis, "harga_diskon": hd, "kategori_id": p["kategori_id"]})
    df = pd.DataFrame(baris)
    df["_u"] = df["level"].map(URUT_LEVEL)
    return df.sort_values(["_u", "sisa_hari"]).drop(columns="_u").reset_index(drop=True)


@df_aman(KOLOM_RISIKO)
def get_risiko_kedaluwarsa() -> pd.DataFrame:
    """Semua batch aktif (termasuk yang 'aman'), terurut dari level paling gawat."""
    return hitung_risiko()[KOLOM_RISIKO]


# ---------------------------------------------------------------------------
# Rekomendasi tindakan
# ---------------------------------------------------------------------------
def sinkron_rekomendasi(risiko: pd.DataFrame) -> dict:
    """Buat / perbarui baris 'menunggu' untuk batch berisiko; hapus yang sudah tidak berisiko.
    Batch yang sudah pernah diputuskan pemilik tidak dibuatkan rekomendasi baru."""
    ada = _db.baca("SELECT id, batch_id, status FROM rekomendasi_tindakan")
    berisiko = risiko[risiko["jenis_tindakan"].notna()].set_index("batch_id") if not risiko.empty else risiko
    dibuat = diperbarui = dihapus = 0
    sekarang = _db.sekarang()
    with _db.get_engine().begin() as conn:
        t = _db.T_REKOMENDASI
        for r in ada[ada["status"] == "menunggu"].itertuples():
            if r.batch_id not in berisiko.index:
                conn.execute(t.delete().where(t.c.id == int(r.id)))
                dihapus += 1
        for bid, r in (berisiko.iterrows() if len(berisiko) else []):
            sudah = ada[ada["batch_id"] == bid]
            nilai = {"jenis": r["jenis_tindakan"], "detail": r["rekomendasi"],
                     "harga_diskon": None if r["harga_diskon"] is None or pd.isna(r["harga_diskon"]) else int(r["harga_diskon"])}
            menunggu = sudah[sudah["status"] == "menunggu"]
            if len(menunggu):
                conn.execute(t.update().where(t.c.id == int(menunggu["id"].iloc[0])).values(**nilai))
                diperbarui += 1
            elif sudah.empty:
                conn.execute(t.insert().values(batch_id=int(bid), status="menunggu", dibuat_pada=sekarang, **nilai))
                dibuat += 1
    return {"dibuat": dibuat, "diperbarui": diperbarui, "dihapus": dihapus}


@df_aman(KOLOM_TINDAKAN)
def get_rekomendasi_tindakan(status=None) -> pd.DataFrame:
    """Rekomendasi tindakan batch berisiko. status=None -> semua (menunggu paling atas);
    atau 'menunggu' / 'disetujui' / 'ditolak' / 'tindakan_lain'. Kolom `id` = rekomendasi_id."""
    risiko = hitung_risiko()
    sinkron_rekomendasi(risiko)
    t = _db.baca("SELECT id, batch_id, jenis, detail, harga_diskon, status, dibuat_pada FROM rekomendasi_tindakan",
                 tanggal=["dibuat_pada"])
    if t.empty:
        return pd.DataFrame(columns=KOLOM_TINDAKAN)
    b = _db.baca("SELECT id AS batch_id, produk_id, tgl_kedaluwarsa, jumlah_sisa AS stok_batch, hpp_satuan "
                 "FROM batch_stok", tanggal=["tgl_kedaluwarsa"])
    p = _db.baca("SELECT id AS produk_id, nama AS nama_produk, harga_jual FROM produk")
    h = hari_ini()
    df = t.merge(b, on="batch_id", how="left").merge(p, on="produk_id", how="left")
    df["sisa_hari"] = (df["tgl_kedaluwarsa"] - h).dt.days
    lv = risiko.set_index("batch_id")[["level", "jumlah_berisiko"]] if not risiko.empty else pd.DataFrame(columns=["level", "jumlah_berisiko"])
    df["level"] = df["batch_id"].map(lv["level"]) if len(lv) else None
    df["jumlah_berisiko"] = df["batch_id"].map(lv["jumlah_berisiko"]) if len(lv) else np.nan
    # keputusan lama (disetujui/ditolak) tetap tampil walau batch sudah aman
    df["level"] = df["level"].fillna("aman")
    if status:
        df = df[df["status"] == status]
    df["_s"] = (df["status"] != "menunggu").astype(int)
    df["_l"] = df["level"].map(URUT_LEVEL).fillna(4)
    df = df.sort_values(["_s", "_l", "sisa_hari"]).reset_index(drop=True)
    return df[KOLOM_TINDAKAN]


def _ambil_rekomendasi(rid):
    df = _db.baca("""SELECT r.id, r.batch_id, r.jenis, r.detail, r.harga_diskon, r.status, b.produk_id
                     FROM rekomendasi_tindakan r LEFT JOIN batch_stok b ON b.id = r.batch_id
                     WHERE r.id = :i""", {"i": int(rid)})
    return None if df.empty else df.iloc[0]


@aksi_aman
def setujui_tindakan(rekomendasi_id) -> dict:
    """Setujui: status 'disetujui', harga diskon tersimpan di rekomendasi_tindakan.harga_diskon,
    dan produk ditandai tunda_pesan = True (dibaca Naila saat membuat draf pesanan)."""
    r = _ambil_rekomendasi(rekomendasi_id)
    if r is None:
        return hasil(False, "Rekomendasi tidak ditemukan")
    if r["status"] != "menunggu":
        return hasil(False, f"Rekomendasi ini sudah berstatus '{r['status']}'")
    with _db.get_engine().begin() as conn:
        conn.execute(_db.T_REKOMENDASI.update().where(_db.T_REKOMENDASI.c.id == int(rekomendasi_id))
                     .values(status="disetujui"))
    if not pd.isna(r["produk_id"]):
        _db.jalankan("UPDATE produk SET tunda_pesan = :v WHERE id = :p", {"v": True, "p": int(r["produk_id"])})
    hd = None if pd.isna(r["harga_diskon"]) else int(r["harga_diskon"])
    return hasil(True, "Tindakan disetujui. Pemesanan produk ini ditunda." + (f" Harga diskon {rp(hd)} tersimpan." if hd else ""),
                 {"rekomendasi_id": int(rekomendasi_id), "batch_id": int(r["batch_id"]), "jenis": r["jenis"],
                  "harga_diskon": hd, "produk_id": None if pd.isna(r["produk_id"]) else int(r["produk_id"])})


@aksi_aman
def tolak_tindakan(rekomendasi_id, tindakan_lain=None) -> dict:
    """Tolak. Kalau `tindakan_lain` diisi, status 'tindakan_lain' dan teksnya ditambahkan ke detail."""
    r = _ambil_rekomendasi(rekomendasi_id)
    if r is None:
        return hasil(False, "Rekomendasi tidak ditemukan")
    if r["status"] != "menunggu":
        return hasil(False, f"Rekomendasi ini sudah berstatus '{r['status']}'")
    lain = (tindakan_lain or "").strip()
    nilai = {"status": "tindakan_lain" if lain else "ditolak"}
    if lain:
        nilai["detail"] = f"{r['detail'] or ''} | Tindakan lain pemilik: {lain}".strip(" |")
    with _db.get_engine().begin() as conn:
        conn.execute(_db.T_REKOMENDASI.update().where(_db.T_REKOMENDASI.c.id == int(rekomendasi_id)).values(**nilai))
    return hasil(True, "Tindakan lain dicatat" if lain else "Rekomendasi ditolak",
                 {"rekomendasi_id": int(rekomendasi_id), "status": nilai["status"], "tindakan_lain": lain or None})
