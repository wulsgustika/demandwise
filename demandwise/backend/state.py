"""Penyimpanan sementara (mock) di st.session_state agar form & alur persetujuan terasa nyata.
Pada versi final, semua isi store ini digantikan tabel database (lihat daftar tabel di README)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from . import mock_data as md


def _now(delta_min: int = 0) -> str:
    return (datetime.now() - timedelta(minutes=delta_min)).strftime("%Y-%m-%d %H:%M")


def now() -> str:
    return _now()


def _seed() -> dict:
    prod = md.produk_df().set_index("produk_id")
    batch = md.batch_df().copy()
    byexp = batch.sort_values("tgl_exp").head(6)

    s: dict = dict(
        batch=batch,
        harga={int(i): float(r.harga) for i, r in prod.iterrows()},
        harga_log=[],
        diskon={},            # batch_id -> dict(persen, harga)
        tunda=set(),          # produk_id yang pemesanannya ditunda
        tindakan={},          # batch_id -> keputusan
        mutasi=[],
        penjualan_baru=[],
        opname_log=[],
        koreksi=[],
        event=md.event_df().copy(),
        laporan_status={},
        next_id=dict(notif=100, tugas=100, po=4, wo=100, biaya=100, koreksi=1),
    )

    # ---- notifikasi awal
    s["notifikasi"] = [
        dict(id=1, role="Manajer", jenis="Risiko", pesan="Ada batch berisiko kedaluwarsa menunggu keputusan tindakan.", waktu=_now(35), dibaca=False),
        dict(id=2, role="Manajer", jenis="Pesanan", pesan="Draf PO-0003 menunggu review Anda.", waktu=_now(80), dibaca=False),
        dict(id=3, role="Pemilik", jenis="Pesanan", pesan="PO-0002 (CV Nusantara Dairy) menunggu persetujuan Pemilik.", waktu=_now(120), dibaca=False),
        dict(id=4, role="Pemilik", jenis="Laporan", pesan="Laporan laba bulan lalu siap diverifikasi Manajer.", waktu=_now(600), dibaca=True),
        dict(id=5, role="Staf Gudang", jenis="Tugas", pesan="Tugas baru: pindahkan batch berisiko ke rak depan.", waktu=_now(45), dibaca=False),
        dict(id=6, role="Staf Gudang", jenis="Stok", pesan="Beberapa produk berstatus menipis. Periksa stok fisik.", waktu=_now(300), dibaca=True),
        dict(id=7, role="Staf Pembelian", jenis="Pesanan", pesan="PO-0001 (UD Tani Makmur) dikirim ke pemasok. Mohon input jadwal kirim.", waktu=_now(240), dibaca=False),
        dict(id=8, role="Staf Pembelian", jenis="Stok", pesan="Peringatan dini: stok beberapa produk di bawah reorder point.", waktu=_now(400), dibaca=False),
        dict(id=9, role="Semua", jenis="Musim", pesan="Event Natal & Tahun Baru: persiapan stok musiman dimulai.", waktu=_now(900), dibaca=False),
    ]

    # ---- tugas gudang
    tugas = []
    for i, r in enumerate(byexp.head(3).itertuples(), start=1):
        nm = prod.loc[r.produk_id, "nama"]
        tugas.append(dict(id=i, judul=f"Pindahkan batch {r.batch_id} ({nm}) ke Rak Depan",
                          detail=f"Batch kedaluwarsa {r.tgl_exp:%d %b %Y}. Prioritaskan agar terjual lebih dulu (FEFO).",
                          jenis="Pindah rak", batch_id=r.batch_id, status="Belum", dibuat=_now(60 * i), selesai=None))
    tugas.append(dict(id=4, judul=f"Siapkan retur ke pemasok untuk batch {byexp.iloc[3].batch_id}",
                      detail="Kemas barang, lampirkan berita acara retur, dan hubungi pemasok.",
                      jenis="Retur pemasok", batch_id=byexp.iloc[3].batch_id, status="Belum", dibuat=_now(200), selesai=None))
    tugas.append(dict(id=5, judul="Pasang label diskon untuk batch yang disetujui",
                      detail="Tempel label harga diskon sesuai keputusan Manajer.", jenis="Label diskon", batch_id="-",
                      status="Selesai", dibuat=_now(1500), selesai=_now(1300)))
    s["tugas"] = tugas

    # ---- pesanan awal
    def items(pairs):
        rows = []
        for pid, q in pairs:
            r = prod.loc[pid]
            rows.append(dict(produk_id=int(pid), nama=r.nama, qty=int(q), hpp=float(r.hpp)))
        return rows

    pid = {n: i for i, n in prod.nama.items() if isinstance(n, str)}
    pid = {v: k for k, v in prod.nama.items()}
    s["pesanan"] = [
        dict(id="PO-0001", pemasok="UD Tani Makmur", status="Dikirim ke Pemasok", dibuat_oleh="Bagas Pratama", dibuat=_now(3000),
             jadwal=None, items=items([(pid["Beras Premium 5kg"], 60), (pid["Gula Pasir 1kg"], 80)]),
             log=[(_now(3000), "Bagas Pratama", "Draf dibuat"), (_now(2900), "Bagas Pratama", "Diajukan ke Manajer"),
                  (_now(2700), "Sari Wulandari", "Diteruskan ke Pemilik"), (_now(2500), "Pak Andi Wijaya", "Disetujui"),
                  (_now(240), "Bagas Pratama", "Dikirim ke pemasok")]),
        dict(id="PO-0002", pemasok="CV Nusantara Dairy", status="Persetujuan Pemilik", dibuat_oleh="Bagas Pratama", dibuat=_now(1000),
             jadwal=None, items=items([(pid["Susu UHT Coklat 200ml"], 150), (pid["Yogurt Cup"], 60), (pid["Keju Slice 10s"], 40)]),
             log=[(_now(1000), "Bagas Pratama", "Draf dibuat"), (_now(900), "Bagas Pratama", "Diajukan ke Manajer"),
                  (_now(120), "Sari Wulandari", "Diteruskan ke Pemilik")]),
        dict(id="PO-0003", pemasok="PT Kue Lestari", status="Review Manajer", dibuat_oleh="Bagas Pratama", dibuat=_now(300),
             jadwal=None, items=items([(pid["Parsel Coklat Natal"], 20), (pid["Hampers Natal Premium"], 12), (pid["Kue Kaleng Assorted"], 25)]),
             log=[(_now(300), "Bagas Pratama", "Draf dibuat"), (_now(90), "Bagas Pratama", "Diajukan ke Manajer")]),
    ]

    # ---- biaya operasional (6 bulan terakhir)
    biaya, k = [], 1
    base = date.today().replace(day=1)
    for m in range(6, -1, -1):
        d0 = (pd.Timestamp(base) - pd.DateOffset(months=m)).date()
        for kat, amt in (("Gaji Karyawan", 21_000_000), ("Sewa Tempat", 8_500_000), ("Listrik & Air", 2_350_000 + 90_000 * (m % 3)),
                         ("Transportasi", 1_600_000 + 70_000 * (m % 4)), ("Lain-lain", 700_000)):
            biaya.append(dict(id=k, tanggal=d0 + timedelta(days=4), kategori=kat, jumlah=float(amt), keterangan="Biaya rutin", oleh="Sari Wulandari"))
            k += 1
    s["biaya"] = biaya

    # ---- write-off awal
    wo = []
    for j, (nm, q, back, why) in enumerate([("Roti Tawar", 6, 12, "Kedaluwarsa"), ("Yogurt Cup", 5, 33, "Kedaluwarsa"),
                                            ("Roti Sobek", 4, 58, "Kedaluwarsa"), ("Jus Jeruk 250ml", 8, 80, "Kedaluwarsa"),
                                            ("Susu UHT Coklat 200ml", 10, 15, "Kedaluwarsa"), ("Telur Ayam 1kg", 3, 45, "Kedaluwarsa")], start=1):
        wo.append(dict(id=j, tanggal=date.today() - timedelta(days=back), produk_id=int(pid[nm]), nama=nm, batch_id="-", qty=q,
                       hpp=float(prod.loc[pid[nm], "hpp"]), alasan=why, oleh="Rina Kusuma"))
    s["writeoff"] = wo

    # ---- riwayat retraining
    s["retrain"] = [
        dict(versi="v1.0", tanggal=_now(60 * 24 * 150)[:10], algoritma="Moving Average (baseline)", mae=4.82, rmse=6.91, mape=21.4, data_latih=9800, catatan="Baseline awal"),
        dict(versi="v1.1", tanggal=_now(60 * 24 * 110)[:10], algoritma="Random Forest", mae=3.95, rmse=5.77, mape=17.3, data_latih=11200, catatan="Tambah fitur kalender"),
        dict(versi="v1.2", tanggal=_now(60 * 24 * 70)[:10], algoritma="Random Forest + event", mae=3.41, rmse=5.02, mape=14.8, data_latih=12600, catatan="Fitur Lebaran/Natal"),
        dict(versi="v1.3", tanggal=_now(60 * 24 * 28)[:10], algoritma="XGBoost + event", mae=3.02, rmse=4.46, mape=12.9, data_latih=13900, catatan="Hyperparameter tuning"),
    ]
    return s


def store() -> dict:
    if "_dw" not in st.session_state:
        st.session_state["_dw"] = _seed()
    return st.session_state["_dw"]


def next_id(key: str) -> int:
    s = store()["next_id"]
    s[key] += 1
    return s[key]
