"""DATA DUMMY (mock) untuk frontend.

Selama backend asli (Wulan & Naila) belum jadi, seluruh halaman memakai fungsi di paket
`backend/` dengan NAMA & RETURN TYPE yang sama dengan kontrak. Ganti isi fungsinya saja
dengan query SQLAlchemy / model ML; halaman tidak perlu diubah.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

TODAY = date.today()
SEED = 2026

# nama, kategori, HPP, margin, masa simpan (hari), rata2 jual/hari, lead time, pemasok, tag musim
_P = [
    ("Air Mineral 600ml", "Minuman", 2200, .30, 365, 46, 2, "PT Sumber Jaya", "umum"),
    ("Teh Botol 450ml", "Minuman", 3800, .26, 240, 30, 2, "PT Sumber Jaya", "umum"),
    ("Susu UHT Coklat 200ml", "Minuman", 4200, .24, 180, 28, 3, "CV Nusantara Dairy", "umum"),
    ("Susu UHT Full Cream 1L", "Minuman", 16500, .18, 180, 14, 3, "CV Nusantara Dairy", "umum"),
    ("Kopi Sachet 10s", "Minuman", 11500, .22, 300, 18, 3, "PT Sumber Jaya", "umum"),
    ("Jus Jeruk 250ml", "Minuman", 5200, .30, 120, 12, 3, "CV Nusantara Dairy", "umum"),
    ("Sirup Marjan 460ml", "Minuman", 17500, .25, 360, 5, 4, "PT Sumber Jaya", "lebaran"),
    ("Minuman Isotonik 500ml", "Minuman", 5800, .28, 270, 15, 2, "PT Sumber Jaya", "umum"),
    ("Beras Premium 5kg", "Makanan Pokok", 68000, .12, 270, 11, 3, "UD Tani Makmur", "lebaran"),
    ("Minyak Goreng 2L", "Makanan Pokok", 33000, .10, 360, 13, 3, "UD Tani Makmur", "lebaran"),
    ("Gula Pasir 1kg", "Makanan Pokok", 14500, .12, 360, 14, 3, "UD Tani Makmur", "lebaran"),
    ("Tepung Terigu 1kg", "Makanan Pokok", 10200, .15, 240, 10, 3, "UD Tani Makmur", "lebaran"),
    ("Mie Instan Goreng", "Makanan Pokok", 2700, .20, 300, 70, 2, "PT Boga Sejahtera", "umum"),
    ("Mie Instan Kuah", "Makanan Pokok", 2600, .20, 300, 62, 2, "PT Boga Sejahtera", "umum"),
    ("Telur Ayam 1kg", "Makanan Pokok", 26000, .10, 21, 17, 1, "UD Tani Makmur", "lebaran"),
    ("Kecap Manis 275ml", "Makanan Pokok", 9800, .22, 360, 8, 3, "PT Boga Sejahtera", "umum"),
    ("Biskuit Kelapa", "Camilan", 7800, .25, 270, 16, 3, "PT Boga Sejahtera", "umum"),
    ("Wafer Coklat", "Camilan", 6200, .27, 240, 19, 3, "PT Boga Sejahtera", "umum"),
    ("Keripik Kentang", "Camilan", 8900, .27, 180, 13, 3, "PT Boga Sejahtera", "umum"),
    ("Kacang Panggang 200g", "Camilan", 12500, .26, 210, 8, 3, "PT Boga Sejahtera", "natal"),
    ("Kue Kaleng Assorted", "Camilan", 58000, .28, 270, 3, 5, "PT Kue Lestari", "lebaran"),
    ("Nastar Kaleng", "Camilan", 72000, .30, 90, 2, 5, "PT Kue Lestari", "lebaran"),
    ("Coklat Batang", "Camilan", 9500, .30, 300, 11, 3, "PT Boga Sejahtera", "natal"),
    ("Parsel Coklat Natal", "Camilan", 95000, .32, 180, 1.5, 6, "PT Kue Lestari", "natal"),
    ("Yogurt Cup", "Susu & Olahan", 6200, .30, 30, 14, 2, "CV Nusantara Dairy", "umum"),
    ("Keju Slice 10s", "Susu & Olahan", 21500, .20, 120, 7, 3, "CV Nusantara Dairy", "natal"),
    ("Roti Tawar", "Susu & Olahan", 11500, .22, 6, 22, 1, "PT Roti Bahagia", "umum"),
    ("Roti Sobek", "Susu & Olahan", 9800, .25, 7, 15, 1, "PT Roti Bahagia", "umum"),
    ("Sosis Siap Makan", "Susu & Olahan", 2400, .35, 60, 20, 2, "CV Nusantara Dairy", "umum"),
    ("Sabun Mandi Batang", "Kebutuhan Rumah", 3300, .25, 720, 16, 3, "PT Rumah Bersih", "umum"),
    ("Shampo Sachet", "Kebutuhan Rumah", 480, .35, 720, 60, 3, "PT Rumah Bersih", "umum"),
    ("Deterjen 800g", "Kebutuhan Rumah", 17800, .18, 720, 9, 3, "PT Rumah Bersih", "lebaran"),
    ("Tisu Gulung 4 roll", "Kebutuhan Rumah", 12800, .22, 720, 10, 3, "PT Rumah Bersih", "umum"),
    ("Pasta Gigi 120g", "Kebutuhan Rumah", 9300, .22, 540, 12, 3, "PT Rumah Bersih", "umum"),
    ("Buku Tulis 38 lembar", "Alat Tulis", 3800, .30, 1000, 24, 4, "CV Cerdas Mandiri", "sekolah"),
    ("Pensil 2B", "Alat Tulis", 2200, .35, 1000, 26, 4, "CV Cerdas Mandiri", "sekolah"),
    ("Pulpen Gel Hitam", "Alat Tulis", 3100, .35, 1000, 22, 4, "CV Cerdas Mandiri", "sekolah"),
    ("Penghapus & Rautan", "Alat Tulis", 1800, .40, 1000, 12, 4, "CV Cerdas Mandiri", "sekolah"),
    ("Kotak Pensil", "Alat Tulis", 14500, .32, 1000, 4, 5, "CV Cerdas Mandiri", "sekolah"),
    ("Hampers Natal Premium", "Camilan", 185000, .30, 150, 1, 7, "PT Kue Lestari", "natal"),
]

KATEGORI = sorted({p[1] for p in _P})
LEBARAN_LALU = date(2026, 3, 20)
NATAL = date(2026, 12, 25)

HITUNG_MUSIM = {"lebaran": 2.8, "natal": 2.4, "sekolah": 2.3, "umum": 1.0}


def musim_factor(tag: str, d: pd.DatetimeIndex) -> np.ndarray:
    """Pengali musiman harian (dipakai simulasi data & baseline prediksi)."""
    dd = pd.DatetimeIndex(d)
    f = np.ones(len(dd))
    # Lebaran 2026 + Lebaran 2027 (10 Mar 2027)
    for leb in (LEBARAN_LALU, date(2027, 3, 10)):
        dt = np.array([(pd.Timestamp(leb) - x).days for x in dd])
        ramp = np.where((dt >= 0) & (dt <= 30), (30 - dt) / 30, np.where((dt < 0) & (dt >= -7), .35, 0))
        amp = {"lebaran": 2.8, "umum": 0.30}.get(tag, 0.0)
        f = f + ramp * (amp if tag != "lebaran" else amp - 1)
    # Natal & akhir tahun
    for nat in (date(2025, 12, 25), NATAL):
        dt = np.array([(pd.Timestamp(nat) - x).days for x in dd])
        ramp = np.where((dt >= 0) & (dt <= 25), (25 - dt) / 25, np.where((dt < 0) & (dt >= -6), .5, 0))
        amp = {"natal": 2.4, "umum": 0.12, "lebaran": 0.0}.get(tag, 0.0)
        f = f + ramp * (amp if tag != "natal" else amp - 1)
    # Tahun ajaran baru (Jul) & semester genap (Jan)
    if tag == "sekolah":
        for c, w in ((date(2026, 7, 14), 20), (date(2027, 7, 12), 20), (date(2027, 1, 11), 10), (date(2026, 1, 12), 10)):
            dt = np.array([abs((pd.Timestamp(c) - x).days) for x in dd])
            f = f + np.where(dt <= w, (w - dt) / w * 1.3, 0)
    return f


def _dow(d: pd.DatetimeIndex) -> np.ndarray:
    return np.array([1.0, .93, .95, .98, 1.08, 1.28, 1.22])[np.array(pd.DatetimeIndex(d).dayofweek)]


@st.cache_data(show_spinner=False)
def produk_df() -> pd.DataFrame:
    rows = []
    for i, p in enumerate(_P, start=1):
        nama, kat, hpp, mg, shelf, base, lt, pem, tag = p
        rows.append(dict(
            produk_id=i, kode=f"DW-{i:03d}", nama=nama, kategori=kat, hpp=float(hpp),
            harga=float(round(hpp * (1 + mg) / 100) * 100), shelf_life=shelf, rata_harian=float(base),
            lead_time=lt, pemasok=pem, tag=tag,
        ))
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def penjualan_harian_df() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    start = pd.Timestamp(TODAY) - pd.Timedelta(days=364)
    idx = pd.date_range(start, pd.Timestamp(TODAY), freq="D")
    out = []
    for r in produk_df().itertuples():
        lam = r.rata_harian * _dow(idx) * musim_factor(r.tag, idx)
        q = rng.poisson(lam * rng.uniform(.93, 1.07))
        out.append(pd.DataFrame({"tanggal": idx, "produk_id": r.produk_id, "qty": q}))
    return pd.concat(out, ignore_index=True)


@st.cache_data(show_spinner=False)
def pemasok_df() -> pd.DataFrame:
    p = produk_df().groupby("pemasok").agg(jumlah_produk=("produk_id", "count"), lead_time=("lead_time", "mean")).reset_index()
    p["lead_time"] = p["lead_time"].round(0).astype(int)
    return p


@st.cache_data(show_spinner=False)
def batch_df() -> pd.DataFrame:
    rng = np.random.default_rng(SEED + 1)
    prod = produk_df()
    cover_choices = [3, 5, 8, 14, 20, 30, 45, 70]
    cover_w = [.12, .14, .16, .20, .14, .10, .08, .06]
    rows, bid = [], 1
    for r in prod.itertuples():
        cover = rng.choice(cover_choices, p=cover_w)
        total = max(4, int(round(r.rata_harian * cover)))
        n = int(rng.choice([1, 2, 3], p=[.35, .45, .20]))
        if r.shelf_life <= 10:
            n = 2
        shares = rng.dirichlet(np.ones(n))
        for k in range(n):
            q = max(2, int(round(total * shares[k])))
            if r.shelf_life <= 10:
                sisa = int(rng.integers(1, r.shelf_life + 1))
            else:
                cand = [d for d in (4, 6, 9, 12, 16, 21, 27, 38, 55, 80, 120, 200, 320, 500) if d <= r.shelf_life]
                sisa = int(rng.choice(cand[max(0, len(cand) - 11):]))
            masuk = TODAY - timedelta(days=int(rng.integers(3, 40)))
            rows.append(dict(batch_id=f"B{bid:04d}", produk_id=r.produk_id, qty=q,
                             tgl_masuk=masuk, tgl_exp=TODAY + timedelta(days=sisa),
                             rak=str(rng.choice(["Rak Depan", "Rak Tengah", "Gudang Belakang"], p=[.3, .4, .3]))))
            bid += 1
    return pd.DataFrame(rows)


def event_df() -> pd.DataFrame:
    return pd.DataFrame([
        dict(event_id=1, nama="Natal & Tahun Baru 2026", mulai=date(2026, 12, 18), selesai=date(2027, 1, 2),
             kategori="Camilan, Susu & Olahan, Minuman", lonjakan=2.2, status="Terkonfirmasi"),
        dict(event_id=2, nama="Ramadan & Lebaran 2027", mulai=date(2027, 2, 8), selesai=date(2027, 3, 17),
             kategori="Makanan Pokok, Minuman, Camilan, Kebutuhan Rumah", lonjakan=2.6, status="Menunggu Konfirmasi"),
        dict(event_id=3, nama="Semester Genap 2027", mulai=date(2027, 1, 4), selesai=date(2027, 1, 25),
             kategori="Alat Tulis", lonjakan=1.7, status="Terkonfirmasi"),
        dict(event_id=4, nama="Tahun Ajaran Baru 2027/2028", mulai=date(2027, 6, 28), selesai=date(2027, 8, 6),
             kategori="Alat Tulis", lonjakan=2.3, status="Menunggu Konfirmasi"),
    ])


USERS = {
    "gudang": dict(nama="Rina Kusuma", role="Staf Gudang", pw="gudang123"),
    "pembelian": dict(nama="Bagas Pratama", role="Staf Pembelian", pw="beli123"),
    "manajer": dict(nama="Sari Wulandari", role="Manajer", pw="manajer123"),
    "pemilik": dict(nama="Pak Andi Wijaya", role="Pemilik", pw="pemilik123"),
}
