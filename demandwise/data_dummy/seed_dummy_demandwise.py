#!/usr/bin/env python3
"""
seed_dummy_demandwise.py  -  Generator data dummy DemandWise (Kelompok 6)

Menghasilkan data 24 bulan (9 Nov 2024 s/d 8 Nov 2026) yang KONSISTEN:
stok disimulasikan hari demi hari (pemasok -> batch -> FEFO -> kedaluwarsa -> write-off),
jadi detail_penjualan, batch_stok, mutasi_stok, writeoff, pesanan saling cocok.

Nama tabel dan kolom mengikuti KONTRAK.md bagian 1.
Jalankan:  python seed_dummy_demandwise.py            (hasil di folder data_dummy/)
"""
import argparse
import math
import os
import sqlite3
from collections import deque, defaultdict
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

SEED = 42
TGL_AWAL = date(2024, 11, 9)
TGL_AKHIR = date(2026, 11, 8)           # "kemarin"; hari ini = 9 Nov 2026
HARI_INI = TGL_AKHIR + timedelta(days=1)
TGL_STOK_AWAL = TGL_AWAL - timedelta(days=1)

# Toko tutup saat Idul Fitri (hari tanpa transaksi = missing value untuk pra-pemrosesan)
TUTUP = {date(2025, 3, 31), date(2025, 4, 1), date(2026, 3, 20), date(2026, 3, 21)}

# ----------------------------------------------------------------------------
# Master data
# ----------------------------------------------------------------------------
KATEGORI = ["Sembako", "Minuman", "Makanan Ringan", "Susu dan Olahan",
            "Roti dan Kue", "Bumbu dan Mi Instan", "Kebersihan", "Alat Tulis"]

# nama, kontak (dummy), lead_time_hari
PEMASOK = [
    ("CV Sumber Pangan Makmur", "081200000001", 3),
    ("PT Segar Minuman Nusantara", "081200000002", 2),
    ("UD Camilan Jaya", "081200000003", 4),
    ("CV Dairy Fresh Sentosa", "081200000004", 2),
    ("Toko Roti Harapan", "081200000005", 1),
    ("Grosir Mitra Rumah Tangga", "081200000006", 3),
    ("CV Pena Cerdas", "081200000007", 5),
]

# Langkah kenaikan harga beli (tanggal, persen)
KENAIKAN_HARGA = [(date(2025, 4, 1), 0.04), (date(2025, 10, 1), 0.03),
                  (date(2026, 4, 1), 0.04), (date(2026, 9, 1), 0.025)]

PESAING = ["Warung Bu Tini", "Toko Maju Jaya", "Minimarket Sejahtera"]

# Jendela musim belanja (perkiraan). Kunci dipakai di dict 'ev' tiap produk.
EVENT_WINDOWS = {
    "natal": [(date(2024, 12, 10), date(2025, 1, 2)), (date(2025, 12, 10), date(2026, 1, 2)),
              (date(2026, 12, 10), date(2027, 1, 2))],
    "ramadan": [(date(2025, 3, 1), date(2025, 3, 30)), (date(2026, 2, 18), date(2026, 3, 19))],
    "lebaran": [(date(2025, 3, 17), date(2025, 4, 3)), (date(2026, 3, 6), date(2026, 3, 23))],
    "tab": [(date(2025, 7, 1), date(2025, 7, 31)), (date(2026, 7, 1), date(2026, 7, 31))],
}
# nama, key, index jendela, sumber  -> tabel event_musiman
EVENT_ROWS = [
    ("Natal dan Tahun Baru 2024/25", "natal", 0, "auto"),
    ("Ramadan 2025", "ramadan", 0, "auto"),
    ("Lebaran 2025", "lebaran", 0, "auto"),
    ("Tahun Ajaran Baru 2025", "tab", 0, "manual"),
    ("Natal dan Tahun Baru 2025/26", "natal", 1, "auto"),
    ("Ramadan 2026", "ramadan", 1, "auto"),
    ("Lebaran 2026", "lebaran", 1, "auto"),
    ("Tahun Ajaran Baru 2026", "tab", 1, "manual"),
    ("Natal dan Tahun Baru 2026/27", "natal", 2, "auto"),
]


def pr(nama, kat, satuan, pem, beli, margin, umur, base, ev=None, pack=1, kemarau=False):
    return dict(nama=nama, kategori_id=kat, satuan=satuan, pemasok_id=pem, beli0=beli,
                margin=margin, umur=umur, base=base, ev=ev or {}, pack=pack, kemarau=kemarau)


PRODUK = [
    # Sembako (kategori 1, pemasok 1)
    pr("Beras Premium 5kg", 1, "kantong", 1, 68000, 0.10, 365, 6, {"ramadan": 1.2, "lebaran": 1.5, "natal": 1.1}, 5),
    pr("Gula Pasir 1kg", 1, "kg", 1, 16500, 0.10, 540, 14, {"ramadan": 1.5, "lebaran": 1.7, "natal": 1.2}, 12),
    pr("Minyak Goreng 1L", 1, "pouch", 1, 15800, 0.08, 365, 18, {"ramadan": 1.3, "lebaran": 1.5, "natal": 1.2}, 12),
    pr("Tepung Terigu 1kg", 1, "kg", 1, 11200, 0.14, 270, 7, {"ramadan": 1.6, "lebaran": 2.2, "natal": 1.7}, 12),
    pr("Telur Ayam 1kg", 1, "kg", 1, 27500, 0.09, 21, 20, {"ramadan": 1.3, "lebaran": 1.6, "natal": 1.4}, 10),
    pr("Garam Dapur 250g", 1, "bungkus", 1, 2800, 0.25, 730, 5, {}, 12),
    pr("Kecap Manis 275ml", 1, "botol", 1, 11500, 0.16, 365, 5, {"lebaran": 1.4, "natal": 1.2}, 12),
    # Minuman (kategori 2, pemasok 2)
    pr("Air Mineral 600ml", 2, "botol", 2, 2200, 0.25, 540, 40, {"lebaran": 1.2}, 24, True),
    pr("Teh Botol 450ml", 2, "botol", 2, 3900, 0.20, 270, 22, {"ramadan": 1.2, "lebaran": 1.3}, 24, True),
    pr("Kopi Sachet Renceng 10s", 2, "renceng", 2, 12500, 0.15, 365, 12, {"natal": 1.1}, 12),
    pr("Sirup Markisa 460ml", 2, "botol", 2, 21000, 0.18, 365, 2.5, {"ramadan": 4.5, "lebaran": 3.5, "natal": 1.6}, 6),
    pr("Minuman Soda 390ml", 2, "botol", 2, 4800, 0.20, 365, 6, {"lebaran": 2.2, "natal": 2.0}, 12),
    pr("Teh Celup 25s", 2, "kotak", 2, 6800, 0.18, 540, 7, {"ramadan": 1.4, "lebaran": 1.4}, 12),
    pr("Jus Kemasan 1L", 2, "kotak", 2, 14500, 0.18, 180, 3, {"natal": 1.3}, 6, True),
    # Makanan ringan (kategori 3, pemasok 3)
    pr("Keripik Kentang 70g", 3, "bungkus", 3, 8300, 0.22, 180, 12, {"natal": 1.4, "lebaran": 1.4}, 12),
    pr("Biskuit Kaleng Assorted 650g", 3, "kaleng", 3, 58000, 0.14, 365, 1.5, {"ramadan": 3.0, "lebaran": 8.0, "natal": 5.0}, 6),
    pr("Wafer Cokelat", 3, "bungkus", 3, 2400, 0.25, 270, 10, {"lebaran": 1.3}, 24),
    pr("Permen Mint Pack", 3, "bungkus", 3, 5200, 0.25, 365, 8, {"lebaran": 1.3, "natal": 1.3}, 12),
    pr("Kacang Atom 200g", 3, "bungkus", 3, 7900, 0.22, 180, 3, {"lebaran": 2.0, "natal": 1.6}, 6),
    pr("Kue Nastar Toples", 3, "toples", 3, 52000, 0.20, 60, 0.8, {"ramadan": 3.0, "lebaran": 12.0, "natal": 3.0}, 1),
    pr("Kurma 500g", 3, "bungkus", 3, 38000, 0.18, 540, 0.7, {"ramadan": 10.0, "lebaran": 5.0}, 1),
    # Susu dan olahan (kategori 4, pemasok 4)
    pr("Susu UHT Cokelat 1L", 4, "kotak", 4, 19500, 0.12, 180, 15, {"natal": 1.1}, 12),
    pr("Susu UHT 200ml", 4, "kotak", 4, 4300, 0.18, 180, 25, {}, 24),
    pr("Susu Kental Manis 370g", 4, "kaleng", 4, 12800, 0.14, 365, 6, {"ramadan": 2.0, "lebaran": 1.6, "natal": 1.5}, 12),
    pr("Yogurt Cup 100g", 4, "cup", 4, 5200, 0.25, 21, 5, {}, 12),
    pr("Keju Slice 10 Lembar", 4, "pak", 4, 21500, 0.18, 120, 2, {"natal": 1.6}, 6),
    # Roti dan kue (kategori 5, pemasok 5)
    pr("Roti Tawar", 5, "bungkus", 5, 12500, 0.20, 6, 14, {"natal": 1.1}, 6),
    pr("Roti Manis Isi", 5, "pcs", 5, 4500, 0.28, 5, 10, {}, 12),
    pr("Bolu Gulung", 5, "pcs", 5, 14500, 0.22, 7, 3, {"lebaran": 1.5, "natal": 1.5}, 3),
    # Bumbu dan mi instan (kategori 6, pemasok 6)
    pr("Mi Instan Goreng", 6, "bungkus", 6, 2900, 0.15, 270, 45, {}, 40),
    pr("Mi Instan Kuah", 6, "bungkus", 6, 2700, 0.15, 270, 38, {}, 40),
    pr("Saus Sambal 135ml", 6, "botol", 6, 5200, 0.20, 365, 6, {"natal": 1.3}, 12),
    pr("Bumbu Racik Serbaguna", 6, "sachet", 6, 1600, 0.30, 365, 9, {"lebaran": 1.5}, 24),
    pr("Kaldu Bubuk 100g", 6, "bungkus", 6, 6200, 0.20, 540, 5, {"lebaran": 1.4}, 12),
    # Kebersihan (kategori 7, pemasok 6)
    pr("Sabun Cuci Piring 400ml", 7, "botol", 6, 9200, 0.18, 730, 6, {"lebaran": 1.3}, 12),
    pr("Deterjen Bubuk 800g", 7, "bungkus", 6, 19500, 0.14, 730, 7, {"lebaran": 1.3}, 12),
    pr("Sabun Mandi Batang", 7, "pcs", 6, 3600, 0.22, 730, 12, {}, 24),
    pr("Sampo Sachet Renceng", 7, "renceng", 6, 8500, 0.20, 730, 10, {}, 12),
    pr("Tisu Gulung 4 Roll", 7, "pak", 6, 11500, 0.20, 730, 3, {"lebaran": 1.3, "natal": 1.2}, 6),
    # Alat tulis (kategori 8, pemasok 7)
    pr("Buku Tulis 38 Lembar", 8, "pcs", 7, 3600, 0.30, 1095, 6, {"tab": 5.0}, 12),
    pr("Pulpen Standar", 8, "pcs", 7, 2000, 0.35, 1095, 8, {"tab": 3.5}, 12),
    pr("Pensil 2B", 8, "pcs", 7, 1800, 0.35, 1095, 4, {"tab": 4.0}, 12),
    pr("Map Plastik Folder", 8, "pcs", 7, 1700, 0.35, 1095, 3, {"tab": 3.0}, 12),
]

WEEKDAY = [0.92, 0.90, 0.93, 0.97, 1.05, 1.22, 1.12]   # Senin..Minggu


# ----------------------------------------------------------------------------
# Fungsi bantu
# ----------------------------------------------------------------------------
def r_beli(x):
    return int(round(x / 50.0) * 50)


def r_jual(x):
    return int(round(x / 100.0) * 100) if x < 10000 else int(round(x / 500.0) * 500)


@lru_cache(maxsize=None)
def shapes(d):
    """Kekuatan tiap musim pada tanggal d (0..1)."""
    out = {}
    for key, wins in EVENT_WINDOWS.items():
        for (s, e) in wins:
            if s <= d <= e:
                L = (e - s).days + 1
                pos = (d - s).days
                if key == "lebaran":
                    out[key] = 0.35 + 0.65 * pos / max(1, L - 1)
                else:
                    out[key] = 0.5 + 0.5 * min(1.0, pos / (0.6 * L))
            elif key == "lebaran" and e < d <= e + timedelta(days=7):
                out["pasca"] = 1.0
    return out


def season_mult(p, d):
    sh = shapes(d)
    m = 1.0
    for k, v in p["ev"].items():
        s = sh.get(k, 0.0)
        if s > 0:
            m = max(m, 1 + (v - 1) * s)
    if sh.get("pasca") and p["ev"].get("lebaran", 1.0) >= 1.3:
        m *= 0.8
    if p["kemarau"] and 6 <= d.month <= 9:
        m *= 1.12
    return m


def harga_pada(steps, d):
    for (tgl, beli, jual) in reversed(steps):
        if tgl <= d:
            return beli, jual
    return steps[0][1], steps[0][2]


def awal_bulan_berikut(d):
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def akhir_bulan(y, m):
    return awal_bulan_berikut(date(y, m, 1)) - timedelta(days=1)


# ----------------------------------------------------------------------------
# Simulasi
# ----------------------------------------------------------------------------
def simulasi(rng):
    # --- siapkan produk
    for i, p in enumerate(PRODUK, start=1):
        p["id"] = i
        p["kode"] = f"PRD-{i:03d}"
        p["lead"] = PEMASOK[p["pemasok_id"] - 1][2]
        p["g"] = 0.08 + rng.uniform(0.0, 0.06)         # pertumbuhan tahunan
        steps = [(TGL_AWAL, p["beli0"], r_jual(p["beli0"] * (1 + p["margin"])))]
        beli = p["beli0"]
        for (tgl, pct) in KENAIKAN_HARGA:
            if rng.random() < 0.85:
                beli = r_beli(beli * (1 + pct * rng.uniform(0.6, 1.4)))
                steps.append((tgl, beli, r_jual(beli * (1 + p["margin"]))))
        p["steps"] = steps
        p["hist"] = deque([p["base"]] * 28, maxlen=28)
        p["pipe"] = []            # pesanan dalam perjalanan
        p["batches"] = []         # batch yang masih punya sisa
        p["retur_jadwal"] = []
        p["mc"] = 1 + min(3.0, p["base"] / 10.0)

    batches, mutasi, writeoffs, opname_rows = [], [], [], []
    orders = []                    # semua order (untuk pesanan_pembelian)
    transaksi, detail = [], []
    lead_cache = {}
    bid = [0]

    def buat_batch(p, tgl_masuk, qty, exp, hpp):
        bid[0] += 1
        b = dict(id=bid[0], produk_id=p["id"], tgl_masuk=tgl_masuk, tgl_kedaluwarsa=exp,
                 jumlah_awal=qty, jumlah_sisa=qty, hpp_satuan=hpp, wo=False)
        batches.append(b)
        p["batches"].append(b)
        return b

    def catat(tgl, pid, batch_id, jenis, qty, ket):
        mutasi.append(dict(tanggal=tgl, produk_id=pid, batch_id=batch_id, jenis=jenis, qty=qty, keterangan=ket))

    # --- stok awal
    for p in PRODUK:
        qty = max(2, int(math.ceil(p["base"] * rng.uniform(7, 12))))
        exp = TGL_STOK_AWAL + timedelta(days=max(4, int(p["umur"] * rng.uniform(0.5, 0.9))))
        hpp = int(round(p["beli0"] * rng.uniform(0.99, 1.01) / 10.0) * 10)
        b = buat_batch(p, TGL_STOK_AWAL, qty, exp, hpp)
        catat(TGL_STOK_AWAL, p["id"], b["id"], "masuk", qty, "Stok awal")

    # --- tanggal opname = hari buka terakhir tiap bulan
    opname_dates = set()
    y, m = TGL_AWAL.year, TGL_AWAL.month
    while date(y, m, 1) <= TGL_AKHIR:
        L = akhir_bulan(y, m)
        while L in TUTUP:
            L -= timedelta(days=1)
        if TGL_AWAL <= L <= TGL_AKHIR:
            opname_dates.add(L)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    # --- loop harian
    d = TGL_AWAL
    while d <= TGL_AKHIR:
        if d in TUTUP:
            d += timedelta(days=1)
            continue
        lines = []   # (produk_id, batch_id, qty, hpp, harga)
        for p in PRODUK:
            pid = p["id"]
            steps = p["steps"]
            # 1. penerimaan barang
            tiba = [o for o in p["pipe"] if o["arr"] <= d]
            for o in tiba:
                p["pipe"].remove(o)
                beli, _ = harga_pada(steps, d)
                hpp = int(round(beli * rng.uniform(0.99, 1.01) / 10.0) * 10)
                aged = int(p["umur"] * rng.uniform(0.0, 0.25))
                exp = d + timedelta(days=max(2, p["umur"] - aged))
                b = buat_batch(p, d, o["qty_final"], exp, hpp)
                o["diterima"] = d
                catat(d, pid, b["id"], "masuk", o["qty_final"], f"Penerimaan dari pemasok (order {o['tgl']})")
                if rng.random() < 0.04 and o["qty_final"] >= 12:
                    p["retur_jadwal"].append((d + timedelta(days=int(rng.integers(1, 4))), b,
                                              int(max(2, o["qty_final"] * rng.uniform(0.03, 0.08)))))
            # 2. retur ke pemasok
            for item in list(p["retur_jadwal"]):
                tgl, b, q = item
                if tgl <= d:
                    p["retur_jadwal"].remove(item)
                    q = min(q, b["jumlah_sisa"])
                    if q > 0:
                        b["jumlah_sisa"] -= q
                        catat(d, pid, b["id"], "retur", -q, "Retur ke pemasok: kemasan rusak")
            # 3. write-off barang kedaluwarsa (dimusnahkan sehari setelah lewat tanggal)
            for b in p["batches"]:
                if b["jumlah_sisa"] > 0 and b["tgl_kedaluwarsa"] < d:
                    q = b["jumlah_sisa"]
                    b["jumlah_sisa"] = 0
                    b["wo"] = True
                    writeoffs.append(dict(tanggal=d, batch_id=b["id"], produk_id=pid, qty=q,
                                          hpp_satuan=b["hpp_satuan"], total_rugi=q * b["hpp_satuan"]))
                    catat(d, pid, b["id"], "writeoff", -q, "Kedaluwarsa dimusnahkan")
            p["batches"] = [b for b in p["batches"] if b["jumlah_sisa"] > 0]
            sellable = sorted([b for b in p["batches"] if b["tgl_kedaluwarsa"] >= d],
                              key=lambda b: (b["tgl_kedaluwarsa"], b["id"]))
            total_sell = sum(b["jumlah_sisa"] for b in sellable)

            # 4. permintaan hari ini
            t_thn = (d - TGL_AWAL).days / 365.0
            wd = WEEKDAY[d.weekday()]
            gajian = 1.07 if (d.day >= 25 or d.day <= 3) else 1.0
            mu = p["base"] * (1 + p["g"] * t_thn) * wd * gajian * season_mult(p, d)
            lam = rng.gamma(10.0, mu / 10.0)
            D = int(rng.poisson(lam))
            if rng.random() < 0.003:
                D = int(D * rng.uniform(2, 3)) + 1
            sold = min(D, total_sell)

            # 5. alokasi FEFO per potongan transaksi
            if sold > 0:
                _, harga = harga_pada(steps, d)
                k = max(1, min(sold, int(round(sold / p["mc"]))))
                extra = sold - k
                parts = np.ones(k, dtype=int)
                if extra > 0:
                    parts += rng.multinomial(extra, [1.0 / k] * k)
                agg = defaultdict(int)
                for q in parts:
                    rem = int(q)
                    for b in sellable:
                        if rem == 0:
                            break
                        if b["jumlah_sisa"] <= 0:
                            continue
                        take = min(rem, b["jumlah_sisa"])
                        b["jumlah_sisa"] -= take
                        rem -= take
                        lines.append((pid, b["id"], take, b["hpp_satuan"], harga))
                        agg[b["id"]] += take
                for b_id, q in agg.items():
                    catat(d, pid, b_id, "penjualan", -q, "Penjualan harian")
            p["hist"].append(sold)

            # 6. barang rusak
            if rng.random() < 0.004:
                q = int(rng.integers(1, 4))
                for b in sellable:
                    if b["jumlah_sisa"] >= q:
                        b["jumlah_sisa"] -= q
                        catat(d, pid, b["id"], "rusak", -q, "Barang rusak/penyok")
                        break

            # 7. keputusan pesan (gaya pemilik: perkiraan kasar dari 28 hari terakhir)
            lead = p["lead"]
            est = float(np.mean(p["hist"]))
            sd = float(np.std(p["hist"]))
            m_now = season_mult(p, d)
            m_fut = season_mult(p, d + timedelta(days=lead + 5))
            est_adj = est * (max(1.0, m_fut / m_now) ** rng.uniform(0.6, 1.1))
            rop = est_adj * (lead + 1) + sd * math.sqrt(lead)
            pos = sum(b["jumlah_sisa"] for b in p["batches"] if b["tgl_kedaluwarsa"] >= d) \
                + sum(o["qty_final"] for o in p["pipe"])
            if pos <= rop and est_adj > 0.05:
                cover = min(9.0, max(1.5, 0.45 * p["umur"]))
                need = est_adj * (lead + 1 + cover) - pos
                if need > 0:
                    pack = p["pack"]
                    qty_rek = int(math.ceil(need / pack) * pack)
                    f = rng.uniform(0.85, 1.3) * (1.8 if rng.random() < 0.06 else 1.0)
                    qty_fin = int(math.ceil(qty_rek * f / pack) * pack)
                    key = (p["pemasok_id"], d)
                    if key not in lead_cache:
                        lead_cache[key] = max(1, lead + int(rng.choice([-1, 0, 0, 0, 1, 2])))
                    o = dict(produk_id=pid, pemasok_id=p["pemasok_id"], tgl=d,
                             arr=d + timedelta(days=lead_cache[key]), qty_rek=qty_rek,
                             qty_final=qty_fin, harga_beli=harga_pada(steps, d)[0], diterima=None)
                    p["pipe"].append(o)
                    orders.append(o)

        # 8. stock opname akhir bulan
        if d in opname_dates:
            idx = rng.choice(len(PRODUK), size=8, replace=False)
            for i in idx:
                p = PRODUK[int(i)]
                sistem = sum(b["jumlah_sisa"] for b in p["batches"])
                delta = int(rng.choice([0, 0, 0, -1, -2, -3, 1, 2]))
                selisih = 0
                if delta < 0:
                    cand = sorted([b for b in p["batches"] if b["jumlah_sisa"] > 0],
                                  key=lambda b: (b["tgl_kedaluwarsa"], b["id"]))
                    if cand:
                        q = min(-delta, cand[0]["jumlah_sisa"])
                        cand[0]["jumlah_sisa"] -= q
                        selisih = -q
                        catat(d, p["id"], cand[0]["id"], "opname", selisih, "Selisih stock opname")
                elif delta > 0:
                    cand = sorted([b for b in p["batches"] if b["jumlah_sisa"] < b["jumlah_awal"]
                                   and b["tgl_kedaluwarsa"] >= d],
                                  key=lambda b: -b["id"])
                    if cand:
                        q = min(delta, cand[0]["jumlah_awal"] - cand[0]["jumlah_sisa"])
                        cand[0]["jumlah_sisa"] += q
                        selisih = q
                        catat(d, p["id"], cand[0]["id"], "opname", selisih, "Selisih stock opname")
                opname_rows.append(dict(tanggal=d, produk_id=p["id"], stok_sistem=sistem,
                                        stok_fisik=sistem + selisih, selisih=selisih))

        # 9. susun transaksi hari ini
        n = len(lines)
        if n > 0:
            n_tx = max(2, min(n, int(n / rng.uniform(4, 7))))
            idx = rng.integers(0, n_tx, size=n)
            grup = defaultdict(list)
            for ln, t in zip(lines, idx):
                grup[int(t)].append(ln)
            for t in sorted(grup):
                tid = len(transaksi) + 1
                total = sum(q * h for (_, _, q, _, h) in grup[t])
                r = rng.random()
                cat = "Pelanggan langganan" if r < 0.03 else ("Pesanan antar" if r < 0.05 else None)
                transaksi.append(dict(id=tid, tanggal=d, total=int(total), catatan=cat))
                for (pid, b_id, q, hpp, h) in grup[t]:
                    detail.append(dict(id=len(detail) + 1, transaksi_id=tid, produk_id=pid,
                                       batch_id=b_id, qty=q, harga_satuan=h, hpp_satuan=hpp))
        d += timedelta(days=1)

    # --- override skenario demo: beberapa batch dibuat mendekati kedaluwarsa (H-3 .. H-29)
    demo = []
    used = set()
    for t in [3, 6, 12, 13, 24, 29]:
        target = HARI_INI + timedelta(days=t)
        best = None
        for b in batches:
            if b["jumlah_sisa"] > 0 and not b["wo"] and b["produk_id"] not in used \
                    and b["tgl_kedaluwarsa"] >= target:
                p = PRODUK[b["produk_id"] - 1]
                ratio = b["jumlah_sisa"] / max(0.1, float(np.mean(p["hist"])) * t)
                if best is None or ratio > best[0]:
                    best = (ratio, b)
        if best:
            best[1]["tgl_kedaluwarsa"] = target
            used.add(best[1]["produk_id"])
            demo.append((PRODUK[best[1]["produk_id"] - 1]["nama"], best[1]["id"], t, best[1]["jumlah_sisa"]))

    return dict(batches=batches, mutasi=mutasi, writeoffs=writeoffs, opname=opname_rows,
                orders=orders, transaksi=transaksi, detail=detail, demo=demo)


# ----------------------------------------------------------------------------
# Bangun tabel sesuai KONTRAK
# ----------------------------------------------------------------------------
def bangun_tabel(sim, rng):
    T = {}
    try:
        import bcrypt
        ph = bcrypt.hashpw(b"demo123", bcrypt.gensalt()).decode()
    except Exception:
        ph = "GANTI_DENGAN_HASH_BCRYPT_DARI_demo123"
    T["users"] = [dict(id=1, username="pemilik", password_hash=ph, nama_usaha="Toko Berkah Jaya",
                       dibuat_pada="2024-11-08 08:00:00")]
    T["kategori"] = [dict(id=i, nama=n) for i, n in enumerate(KATEGORI, 1)]
    T["pemasok"] = [dict(id=i, nama=n, kontak=k, lead_time_hari=l) for i, (n, k, l) in enumerate(PEMASOK, 1)]

    T["produk"], T["harga_jual"], T["harga_pesaing"] = [], [], []
    hj_id = hp_id = 0
    tgl_pesaing = [date(2024 + (m + 10) // 12, (m + 10) % 12 + 1, 15) for m in range(24)] + [date(2026, 11, 5)]
    for p in PRODUK:
        beli_akhir, jual_akhir = p["steps"][-1][1], p["steps"][-1][2]
        T["produk"].append(dict(id=p["id"], kode=p["kode"], nama=p["nama"], kategori_id=p["kategori_id"],
                                satuan=p["satuan"], pemasok_id=p["pemasok_id"],
                                harga_beli_terakhir=beli_akhir, harga_jual=jual_akhir,
                                umur_simpan_hari=p["umur"], lead_time_hari=p["lead"],
                                aktif=True, tunda_pesan=False))
        for (tgl, beli, jual) in p["steps"]:
            hj_id += 1
            T["harga_jual"].append(dict(id=hj_id, produk_id=p["id"], harga=jual, berlaku_mulai=tgl, sumber="manual"))
        for tgl in tgl_pesaing:
            _, jual = harga_pada(p["steps"], tgl)
            for nm in PESAING:
                hp_id += 1
                T["harga_pesaing"].append(dict(id=hp_id, produk_id=p["id"], nama_pesaing=nm,
                                               harga=r_jual(jual * rng.uniform(0.95, 1.08)), tanggal=tgl))

    # batch_stok
    rows = []
    for b in sorted(sim["batches"], key=lambda x: x["id"]):
        if b["wo"]:
            st = "kedaluwarsa"
        elif b["jumlah_sisa"] == 0:
            st = "habis"
        else:
            st = "aktif"
        rows.append(dict(id=b["id"], produk_id=b["produk_id"], tgl_masuk=b["tgl_masuk"],
                         tgl_kedaluwarsa=b["tgl_kedaluwarsa"], jumlah_awal=b["jumlah_awal"],
                         jumlah_sisa=b["jumlah_sisa"], hpp_satuan=b["hpp_satuan"], status=st))
    T["batch_stok"] = rows
    T["transaksi_penjualan"] = sim["transaksi"]
    T["detail_penjualan"] = sim["detail"]

    mut = sorted(sim["mutasi"], key=lambda x: (x["tanggal"],))
    T["mutasi_stok"] = [dict(id=i, **m) for i, m in enumerate(mut, 1)]
    T["stock_opname"] = [dict(id=i, **o) for i, o in enumerate(sim["opname"], 1)]
    T["writeoff"] = [dict(id=i, **w) for i, w in enumerate(sorted(sim["writeoffs"], key=lambda x: x["tanggal"]), 1)]

    # biaya operasional
    biaya, bid = [], 0

    def tambah(tgl, kat, jumlah, ket):
        nonlocal bid
        if TGL_AWAL <= tgl <= TGL_AKHIR:
            bid += 1
            biaya.append(dict(id=bid, tanggal=tgl, kategori_biaya=kat, jumlah=int(jumlah), keterangan=ket))

    y, m = 2024, 11
    while date(y, m, 1) <= TGL_AKHIR:
        tambah(date(y, m, 1), "Sewa Toko", 3500000, "Sewa bulanan")
        tambah(date(y, m, 5), "Internet dan Pulsa", 300000, "Paket internet toko")
        tambah(date(y, m, 10), "Kemasan dan Plastik", int(rng.integers(400, 651)) * 1000, "Kantong plastik dan kemasan")
        tambah(date(y, m, 15), "Transportasi", int(rng.integers(1200, 1801)) * 1000, "Bensin dan ongkos kirim")
        tambah(date(y, m, 20), "Listrik", int(rng.integers(1100, 1501)) * 1000, "Tagihan listrik")
        tambah(date(y, m, 20), "Air", int(rng.integers(200, 261)) * 1000, "Tagihan air")
        tambah(date(y, m, 28), "Gaji Karyawan", 6000000, "Gaji 2 karyawan")
        if rng.random() < 0.5:
            tambah(date(y, m, 22), "Lain-lain", int(rng.integers(50, 401)) * 1000, "Perawatan dan kebutuhan kecil")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    tambah(date(2025, 3, 24), "Gaji Karyawan", 6000000, "THR karyawan")
    tambah(date(2026, 3, 12), "Gaji Karyawan", 6000000, "THR karyawan")
    biaya.sort(key=lambda x: x["tanggal"])
    for i, r in enumerate(biaya, 1):
        r["id"] = i
    T["biaya_operasional"] = biaya

    # event_musiman
    ev = []
    for i, (nama, key, wi, sumber) in enumerate(EVENT_ROWS, 1):
        s, e = EVENT_WINDOWS[key][wi]
        ev.append(dict(id=i, nama=nama, tgl_mulai=s, tgl_selesai=e, sumber=sumber))
    T["event_musiman"] = ev

    # pesanan_pembelian dan detail_pesanan
    grup = defaultdict(list)
    for o in sim["orders"]:
        grup[(o["tgl"], o["pemasok_id"])].append(o)
    pesanan, dp = [], []
    for pid_, key in enumerate(sorted(grup), 1):
        tgl, pem = key
        os_ = grup[key]
        if all(o["diterima"] for o in os_):
            st = "diterima"
        else:
            st = "dikirim" if tgl < TGL_AKHIR else "dipesan"
        pesanan.append(dict(id=pid_, pemasok_id=pem, tanggal=tgl, status=st,
                            jadwal_kirim=os_[0]["arr"], catatan="Dipesan lewat WhatsApp"))
        for o in os_:
            dp.append(dict(id=len(dp) + 1, pesanan_id=pid_, produk_id=o["produk_id"],
                           qty_rekomendasi=o["qty_rek"], qty_final=o["qty_final"], harga_beli=o["harga_beli"]))
    T["pesanan_pembelian"] = pesanan
    T["detail_pesanan"] = dp
    return T


KOLOM = {
    "users": ["id", "username", "password_hash", "nama_usaha", "dibuat_pada"],
    "kategori": ["id", "nama"],
    "pemasok": ["id", "nama", "kontak", "lead_time_hari"],
    "produk": ["id", "kode", "nama", "kategori_id", "satuan", "pemasok_id", "harga_beli_terakhir",
               "harga_jual", "umur_simpan_hari", "lead_time_hari", "aktif", "tunda_pesan"],
    "batch_stok": ["id", "produk_id", "tgl_masuk", "tgl_kedaluwarsa", "jumlah_awal", "jumlah_sisa",
                   "hpp_satuan", "status"],
    "transaksi_penjualan": ["id", "tanggal", "total", "catatan"],
    "detail_penjualan": ["id", "transaksi_id", "produk_id", "batch_id", "qty", "harga_satuan", "hpp_satuan"],
    "mutasi_stok": ["id", "tanggal", "produk_id", "batch_id", "jenis", "qty", "keterangan"],
    "stock_opname": ["id", "tanggal", "produk_id", "stok_sistem", "stok_fisik", "selisih"],
    "biaya_operasional": ["id", "tanggal", "kategori_biaya", "jumlah", "keterangan"],
    "writeoff": ["id", "tanggal", "batch_id", "produk_id", "qty", "hpp_satuan", "total_rugi"],
    "event_musiman": ["id", "nama", "tgl_mulai", "tgl_selesai", "sumber"],
    "harga_jual": ["id", "produk_id", "harga", "berlaku_mulai", "sumber"],
    "harga_pesaing": ["id", "produk_id", "nama_pesaing", "harga", "tanggal"],
    "pesanan_pembelian": ["id", "pemasok_id", "tanggal", "status", "jadwal_kirim", "catatan"],
    "detail_pesanan": ["id", "pesanan_id", "produk_id", "qty_rekomendasi", "qty_final", "harga_beli"],
}


def ke_df(rows, cols):
    df = pd.DataFrame(rows)[cols]
    for c in df.columns:
        if df[c].dtype == object and len(df) and isinstance(df[c].iloc[0], date):
            df[c] = df[c].map(lambda x: x.isoformat())
    return df


# ----------------------------------------------------------------------------
# Validasi
# ----------------------------------------------------------------------------
def validasi(D):
    msg = []
    b, m, det, tx = D["batch_stok"], D["mutasi_stok"], D["detail_penjualan"], D["transaksi_penjualan"]
    # 1. sisa batch = jumlah mutasi per batch
    s = m.groupby("batch_id")["qty"].sum()
    ok1 = (b.set_index("id")["jumlah_sisa"] == s.reindex(b["id"]).values).all()
    msg.append(("jumlah_sisa batch = total mutasi per batch", ok1))
    # 2. tidak ada stok negatif
    msg.append(("tidak ada jumlah_sisa negatif", (b["jumlah_sisa"] >= 0).all()))
    # 3. detail penjualan = mutasi penjualan
    a = det["qty"].sum()
    c = -m[m["jenis"] == "penjualan"]["qty"].sum()
    msg.append(("total qty detail_penjualan = mutasi penjualan", a == c))
    # 4. total transaksi = jumlah detail
    t = det.assign(x=det["qty"] * det["harga_satuan"]).groupby("transaksi_id")["x"].sum()
    msg.append(("transaksi.total = sum(qty x harga)", (tx.set_index("id")["total"] == t.reindex(tx["id"]).values).all()))
    # 5. FK
    msg.append(("FK detail->batch/produk/transaksi", det["batch_id"].isin(b["id"]).all()
                and det["produk_id"].isin(D["produk"]["id"]).all()
                and det["transaksi_id"].isin(tx["id"]).all()))
    # 6. penjualan tidak memakai batch kedaluwarsa
    j = det.merge(tx[["id", "tanggal"]], left_on="transaksi_id", right_on="id").merge(
        b[["id", "tgl_kedaluwarsa", "tgl_masuk"]], left_on="batch_id", right_on="id", suffixes=("", "_b"))
    msg.append(("tidak ada penjualan dari batch yang sudah kedaluwarsa", (j["tanggal"] <= j["tgl_kedaluwarsa"]).all()))
    msg.append(("tidak ada penjualan sebelum batch masuk", (j["tanggal"] >= j["tgl_masuk"]).all()))
    return msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data_dummy")
    ap.add_argument("--tanpa-sqlite", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rng = np.random.default_rng(SEED)

    sim = simulasi(rng)
    T = bangun_tabel(sim, rng)
    D = {n: ke_df(T[n], KOLOM[n]) for n in KOLOM}

    for n, df in D.items():
        df.to_csv(os.path.join(args.out, f"{n}.csv"), index=False)
    if not args.tanpa_sqlite:
        path = os.path.join(args.out, "demandwise_dummy.sqlite")
        if os.path.exists(path):
            os.remove(path)
        con = sqlite3.connect(path)
        for n, df in D.items():
            df.to_sql(n, con, index=False)
        con.close()

    # ---- ringkasan
    print("=" * 60)
    print("TABEL DAN JUMLAH BARIS")
    for n, df in D.items():
        print(f"  {n:22s} {len(df):>8,}")
    print("\nVALIDASI")
    for teks, ok in validasi(D):
        print(f"  [{'OK' if ok else 'GAGAL'}] {teks}")

    det, tx = D["detail_penjualan"], D["transaksi_penjualan"]
    tx = tx.assign(bulan=tx["tanggal"].str[:7])
    pj = tx.groupby("bulan")["total"].sum()
    hpp = det.merge(D["transaksi_penjualan"][["id", "tanggal"]], left_on="transaksi_id", right_on="id")
    hpp["bulan"] = hpp["tanggal"].str[:7]
    hpp["h"] = hpp["qty"] * hpp["hpp_satuan"]
    hp = hpp.groupby("bulan")["h"].sum()
    wo = D["writeoff"].assign(bulan=D["writeoff"]["tanggal"].str[:7]).groupby("bulan")["total_rugi"].sum()
    bi = D["biaya_operasional"].assign(bulan=D["biaya_operasional"]["tanggal"].str[:7]).groupby("bulan")["jumlah"].sum()
    rk = pd.DataFrame({"penjualan": pj, "hpp": hp, "writeoff": wo, "biaya": bi}).fillna(0).astype(int)
    rk["laba_bersih"] = rk["penjualan"] - rk["hpp"] - rk["biaya"] - rk["writeoff"]
    print("\nRINGKASAN PER BULAN (Rp)")
    print(rk.to_string())
    print(f"\nTotal penjualan 24 bulan : Rp {rk['penjualan'].sum():,}")
    print(f"Total write-off          : Rp {rk['writeoff'].sum():,}  ({rk['writeoff'].sum() / rk['penjualan'].sum():.2%} dari penjualan)")
    print("\nSKENARIO DEMO (batch dibuat mendekati kedaluwarsa)")
    for nama, b_id, t, sisa in sim["demo"]:
        lvl = "kritis" if t <= 7 else "siaga" if t <= 14 else "waspada"
        print(f"  batch {b_id:>4}  {nama:30s} H-{t:<2} ({lvl})  sisa {sisa}")
    print("=" * 60)


if __name__ == "__main__":
    main()
