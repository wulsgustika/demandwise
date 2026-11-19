"""Indeks musim, event musiman, dan notifikasi musim mendekat."""
import numpy as np
import pandas as pd

from . import _db, _integrasi, data_akses as da, k
from ._util import aksi_aman, df_aman, hari_ini, hasil, rp, tgl_id
from .model_prediksi import tipe_event

KOLOM_INDEKS = ["produk_id", "nama_produk", "bulan", "indeks", "event_terkait"]
KOLOM_EVENT = ["id", "nama", "tgl_mulai", "tgl_selesai", "sumber"]

# Perkiraan jendela musim (jendela Lebaran = 14 hari sebelum s/d 3 hari sesudah Idul Fitri,
# mengikuti pola data dummy). Kalender hijriah = PERKIRAAN: koreksi lewat simpan_event / tabel.
_LUNAR = {
    2024: {"Ramadan": ("2024-03-11", "2024-04-09"), "Lebaran": ("2024-03-27", "2024-04-13")},
    2025: {"Ramadan": ("2025-03-01", "2025-03-30"), "Lebaran": ("2025-03-17", "2025-04-03")},
    2026: {"Ramadan": ("2026-02-18", "2026-03-19"), "Lebaran": ("2026-03-06", "2026-03-23")},
    2027: {"Ramadan": ("2027-02-08", "2027-03-09"), "Lebaran": ("2027-02-24", "2027-03-13")},
    2028: {"Ramadan": ("2028-01-28", "2028-02-26"), "Lebaran": ("2028-02-13", "2028-03-01")},
}


def _kandidat_event(tahun: int) -> list:
    """(nama, mulai, selesai) yang 'seharusnya' ada pada tahun tsb (sumber auto)."""
    out = [(f"Natal dan Tahun Baru {tahun}/{(tahun + 1) % 100:02d}",
            pd.Timestamp(tahun, 12, 10), pd.Timestamp(tahun + 1, 1, 2)),
           (f"Tahun Ajaran Baru {tahun}", pd.Timestamp(tahun, 7, 1), pd.Timestamp(tahun, 7, 31))]
    for nm, (a, b) in _LUNAR.get(tahun, {}).items():
        out.append((f"{nm} {tahun}", pd.Timestamp(a), pd.Timestamp(b)))
    return out


def pastikan_event_otomatis(h=None, pv_index=None):
    """Lengkapi event_musiman (sumber 'auto') untuk tahun-tahun yang belum ada. Aman dipanggil berulang."""
    h = h if h is not None else hari_ini()
    ev = da.events()
    ada = {(tipe_event(r.nama), r.tgl_mulai.year) for r in ev.itertuples()}
    if pv_index is None or len(pv_index) == 0:
        pv_index, _ = da.penjualan_harian_matriks()[0].index, None
    tgl_data_awal = pv_index.min() if len(pv_index) else h
    awal = tgl_data_awal.year
    baru = []
    for th in range(awal, h.year + 3):
        for nama, a, b in _kandidat_event(th):
            if (tipe_event(nama), a.year) in ada or b < tgl_data_awal:
                continue
            baru.append({"nama": nama, "tgl_mulai": a.date(), "tgl_selesai": b.date(), "sumber": "auto"})
    _db.sisip(_db.T_EVENT, baru)
    return len(baru)


@df_aman(KOLOM_EVENT)
def get_event_musiman() -> pd.DataFrame:
    pastikan_event_otomatis()
    ev = da.events()[KOLOM_EVENT]
    return ev.sort_values("tgl_mulai").reset_index(drop=True)


@aksi_aman
def simpan_event(nama, tgl_mulai, tgl_selesai) -> dict:
    nama = (nama or "").strip()
    if not nama:
        return hasil(False, "Nama event wajib diisi")
    try:
        a, b = pd.Timestamp(tgl_mulai).normalize(), pd.Timestamp(tgl_selesai).normalize()
    except Exception:
        return hasil(False, "Format tanggal tidak valid (gunakan YYYY-MM-DD)")
    if pd.isna(a) or pd.isna(b):
        return hasil(False, "Format tanggal tidak valid (gunakan YYYY-MM-DD)")
    if a > b:
        return hasil(False, "Tanggal mulai tidak boleh setelah tanggal selesai")
    ev = da.events()
    dup = ev[(ev["nama"].str.lower() == nama.lower()) & (ev["tgl_mulai"] == a)]
    if not dup.empty:
        return hasil(False, "Event dengan nama dan tanggal mulai yang sama sudah ada")
    _db.sisip(_db.T_EVENT, [{"nama": nama, "tgl_mulai": a.date(), "tgl_selesai": b.date(), "sumber": "manual"}])
    return hasil(True, "Event musiman tersimpan. Berlaku pada prediksi berikutnya (jalankan prediksi / latih ulang).",
                 {"nama": nama, "tgl_mulai": str(a.date()), "tgl_selesai": str(b.date())})


# ---------------------------------------------------------------------------
# Indeks musim
# ---------------------------------------------------------------------------
def hitung_indeks_musim(pv: pd.DataFrame = None, tutup=None, simpan=True) -> pd.DataFrame:
    """indeks(bulan) = rata-rata penjualan harian pada bulan itu / rata-rata harian seluruh bulan.
    Hari toko tutup tidak dihitung. Bulan tanpa data -> indeks 1,0."""
    if pv is None:
        pv, tutup = da.penjualan_harian_matriks()
    if pv.empty:
        return pd.DataFrame(columns=["produk_id", "bulan", "indeks"])
    buka = pv.loc[~pv.index.isin(tutup if tutup is not None else [])]
    rata_all = buka.mean()
    per_bulan = buka.groupby(buka.index.month).mean().reindex(range(1, 13))
    baris = []
    for pid in pv.columns:
        ra = rata_all[pid]
        for b in range(1, 13):
            v = per_bulan.at[b, pid]
            idx = 1.0 if (ra <= 0 or pd.isna(v)) else float(v / ra)
            baris.append({"produk_id": int(pid), "bulan": b, "indeks": round(idx, 3)})
    df = pd.DataFrame(baris)
    if simpan:
        with _db.get_engine().begin() as conn:
            conn.execute(_db.T_INDEKS_MUSIM.delete())
            conn.execute(_db.T_INDEKS_MUSIM.insert(), baris)
    return df


def _label_event(nama: str) -> str:
    return " ".join(w.capitalize() if w != "dan" else w for w in tipe_event(nama).split())


def _event_per_bulan(ev: pd.DataFrame) -> dict:
    peta = {b: [] for b in range(1, 13)}
    for r in ev.itertuples():
        for per in pd.period_range(r.tgl_mulai, r.tgl_selesai, freq="M"):
            lab = _label_event(r.nama)
            if lab not in peta[per.month]:
                peta[per.month].append(lab)
    return peta


@df_aman(KOLOM_INDEKS)
def get_indeks_musim() -> pd.DataFrame:
    idx = _db.baca("SELECT produk_id, bulan, indeks FROM indeks_musim")
    if idx.empty:
        idx = hitung_indeks_musim()
    prod = da.semua_produk()
    df = idx.merge(prod, on="produk_id", how="left")
    peta = _event_per_bulan(da.events())
    df["event_terkait"] = df["bulan"].map(lambda b: ", ".join(peta.get(int(b), [])))
    return df[KOLOM_INDEKS].sort_values(["produk_id", "bulan"]).reset_index(drop=True)



# ---------------------------------------------------------------------------
# Rekomendasi stok musiman (swimlane bagian 6: tetap dibatasi masa simpan).
# INTERNAL: dipakai untuk isi notifikasi `musim_mendekat`, bukan fungsi kontrak.
# ---------------------------------------------------------------------------
KOLOM_STOK_MUSIM = ["event_id", "event", "tgl_mulai", "sisa_hari", "produk_id", "nama_produk", "indeks_musim",
                    "stok_saat_ini", "prediksi_harian_musim", "kebutuhan_musim", "pesanan_berjalan",
                    "batas_masa_simpan", "qty_rekomendasi", "ditunda"]


def hitung_stok_musiman(h=None, horizon_hari=None) -> pd.DataFrame:
    """Untuk tiap event yang mulai <= horizon_hari (bawaan H-30) dan tiap produk berindeks musim > 1,2:
      prediksi_harian_musim = qty/hari normal (90 hari terakhir) x indeks musim event
      stok proyeksi awal    = stok sekarang - qty/hari normal x sisa hari menuju event (tidak negatif)
      kebutuhan_musim       = prediksi_harian_musim x durasi event + safety stock - stok proyeksi - pesanan berjalan
      batas_masa_simpan     = prediksi_harian_musim x umur simpan produk  (definisi batas masa simpan, KONTRAK bagian 4)
      qty_rekomendasi       = min(kebutuhan_musim, batas_masa_simpan), minimal 0
    """
    from .profit import tabel_kecepatan
    from .stok import hitung_stok_status
    h = h if h is not None else hari_ini()
    horizon = int(horizon_hari if horizon_hari is not None else k.LEVEL_WASPADA_HARI)
    ev = da.events()
    ev = ev[(ev["tgl_mulai"] >= h) & ((ev["tgl_mulai"] - h).dt.days <= horizon)]
    if ev.empty:
        return pd.DataFrame(columns=KOLOM_STOK_MUSIM)
    idx = _db.baca("SELECT produk_id, bulan, indeks FROM indeks_musim")
    if idx.empty:
        idx = hitung_indeks_musim()
    prod = da.produk_aktif().set_index("produk_id")
    st = hitung_stok_status(h).set_index("produk_id")
    kec = tabel_kecepatan(h=h).set_index("produk_id")["qty_per_hari"]
    jalan = _db.baca("""SELECT d.produk_id, SUM(COALESCE(d.qty_final, d.qty_rekomendasi)) AS qty
                        FROM detail_pesanan d JOIN pesanan_pembelian p ON p.id = d.pesanan_id
                        WHERE p.status IN ('dipesan', 'dikirim') GROUP BY d.produk_id""")
    jalan = jalan.set_index("produk_id")["qty"] if len(jalan) else pd.Series(dtype=float)
    baris = []
    for r in ev.itertuples():
        bulan_event = sorted({p.month for p in pd.period_range(r.tgl_mulai, r.tgl_selesai, freq="M")})
        sisa = int((r.tgl_mulai - h).days)
        durasi = int((r.tgl_selesai - r.tgl_mulai).days) + 1
        ind = idx[idx["bulan"].isin(bulan_event)].groupby("produk_id")["indeks"].max()
        for pid, nilai in ind.items():
            if nilai <= k.AMBANG_INDEKS_MUSIM_LARIS or pid not in prod.index or pid not in st.index:
                continue
            normal = float(kec.get(pid, 0.0))
            harian = normal * float(nilai)
            stok_awal = max(0.0, float(st.at[pid, "stok_saat_ini"]) - normal * sisa)
            berjalan = float(jalan.get(pid, 0.0))
            kebutuhan = max(0.0, harian * durasi + float(st.at[pid, "safety_stock"]) - stok_awal - berjalan)
            batas = harian * float(prod.at[pid, "umur_simpan_hari"])
            baris.append({"event_id": int(r.id), "event": r.nama, "tgl_mulai": r.tgl_mulai, "sisa_hari": sisa,
                          "produk_id": int(pid), "nama_produk": prod.at[pid, "nama_produk"],
                          "indeks_musim": round(float(nilai), 3), "stok_saat_ini": int(st.at[pid, "stok_saat_ini"]),
                          "prediksi_harian_musim": round(harian, 2), "kebutuhan_musim": int(round(kebutuhan)),
                          "pesanan_berjalan": int(round(berjalan)), "batas_masa_simpan": int(round(batas)),
                          "qty_rekomendasi": int(round(max(0.0, min(kebutuhan, batas)))),
                          "ditunda": str(prod.at[pid, "tunda_pesan"]).lower() in ("1", "true", "t")})
    if not baris:
        return pd.DataFrame(columns=KOLOM_STOK_MUSIM)
    df = pd.DataFrame(baris, columns=KOLOM_STOK_MUSIM)
    return df.sort_values(["sisa_hari", "qty_rekomendasi"], ascending=[True, False]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Notifikasi musim mendekat (indeks > 1,2 pada H-30)
# ---------------------------------------------------------------------------
def periksa_musim_mendekat(h=None) -> int:
    h = h if h is not None else hari_ini()
    ev = da.events()
    ev = ev[(ev["tgl_mulai"] >= h) & ((ev["tgl_mulai"] - h).dt.days <= k.LEVEL_WASPADA_HARI)]
    if ev.empty:
        return 0
    idx = _db.baca("SELECT produk_id, bulan, indeks FROM indeks_musim")
    if idx.empty:
        idx = hitung_indeks_musim()
    nama = da.produk_aktif().set_index("produk_id")["nama_produk"]
    rek = hitung_stok_musiman(h)
    qty_rek = {(int(a), int(b)): (int(c), int(d)) for a, b, c, d in
               zip(rek["event_id"], rek["produk_id"], rek["qty_rekomendasi"], rek["batas_masa_simpan"])}
    terkirim = 0
    for r in ev.itertuples():
        bulan_event = sorted({p.month for p in pd.period_range(r.tgl_mulai, r.tgl_selesai, freq="M")})
        sisa = (r.tgl_mulai - h).days
        sub = idx[idx["bulan"].isin(bulan_event)].groupby("produk_id")["indeks"].max()
        for pid, ind in sub.items():
            if ind <= k.AMBANG_INDEKS_MUSIM_LARIS or pid not in nama.index:
                continue
            judul = f"Musim laris mendekat: {nama[pid]}"
            pesan = (f"{r.nama} mulai {tgl_id(r.tgl_mulai)} (H-{sisa}). Indeks musim {nama[pid]} "
                     f"{ind:.2f}".replace(".", ",") + f" (di atas {str(k.AMBANG_INDEKS_MUSIM_LARIS).replace('.', ',')}). "
                     "Siapkan stok musiman, tetap batasi sesuai masa simpan.")
            if (int(r.id), int(pid)) in qty_rek:
                q, bts = qty_rek[(int(r.id), int(pid))]
                pesan += f" Rekomendasi tambahan stok {q} unit (batas masa simpan {bts} unit)."
            if _integrasi.kirim("musim_mendekat", "info", judul, pesan, "event_musiman", int(r.id), dedupe="semua"):
                terkirim += 1
    return terkirim
