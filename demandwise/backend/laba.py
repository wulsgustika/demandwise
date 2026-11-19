"""backend/laba.py - laporan laba (pemilik: Naila). KONTRAK 3.7 dan bagian 4.

Rumus (satu-satunya definisi laba, dipakai juga oleh dashboard Wulan):
  Penjualan   = SUM(qty x harga_satuan)  dari detail_penjualan
  HPP         = SUM(qty x hpp_satuan)    dari detail_penjualan (HPP batch yang terjual,
                bukan harga beli terakhir)
  Laba Kotor  = Penjualan - HPP
  Biaya Op.   = SUM(jumlah)              dari biaya_operasional
  Write-off   = SUM(total_rugi)          dari writeoff
  Laba Bersih = Laba Kotor - Biaya Operasional - Write-off
Periode: tgl_awal sampai tgl_akhir, keduanya ikut dihitung.
"""
from datetime import date

import pandas as pd
from sqlalchemy import func, select

from .models import BiayaOperasional, DetailPenjualan, TransaksiPenjualan, Writeoff

KOMPONEN = ["Penjualan", "HPP", "Laba Kotor", "Biaya Operasional",
            "Kerugian Kedaluwarsa (Write-off)", "Laba Bersih"]


def hitung_laba_di(s, tgl_awal: date, tgl_akhir: date) -> dict:
    """Hitung semua angka laba. Return dict berisi int."""
    jual = s.execute(
        select(func.coalesce(func.sum(DetailPenjualan.qty * DetailPenjualan.harga_satuan), 0),
               func.coalesce(func.sum(DetailPenjualan.qty * DetailPenjualan.hpp_satuan), 0))
        .join(TransaksiPenjualan, TransaksiPenjualan.id == DetailPenjualan.transaksi_id)
        .where(TransaksiPenjualan.tanggal.between(tgl_awal, tgl_akhir))).one()
    biaya = s.scalar(select(func.coalesce(func.sum(BiayaOperasional.jumlah), 0))
                     .where(BiayaOperasional.tanggal.between(tgl_awal, tgl_akhir)))
    rugi = s.scalar(select(func.coalesce(func.sum(Writeoff.total_rugi), 0))
                    .where(Writeoff.tanggal.between(tgl_awal, tgl_akhir)))
    penjualan, hpp = int(jual[0]), int(jual[1])
    kotor = penjualan - hpp
    return {"Penjualan": penjualan, "HPP": hpp, "Laba Kotor": kotor,
            "Biaya Operasional": int(biaya),
            "Kerugian Kedaluwarsa (Write-off)": int(rugi),
            "Laba Bersih": kotor - int(biaya) - int(rugi)}


def get_laporan_laba_di(s, tgl_awal: date, tgl_akhir: date) -> pd.DataFrame:
    angka = hitung_laba_di(s, tgl_awal, tgl_akhir)
    return pd.DataFrame({"komponen": KOMPONEN, "jumlah": [angka[k] for k in KOMPONEN]})


def get_laporan_laba(tgl_awal: date, tgl_akhir: date) -> pd.DataFrame:
    """Fungsi KONTRAK 2.2 (dipakai Dhea). Tanggal salah/error -> DataFrame kosong
    dengan kolom yang sama (tidak melempar error ke layar, KONTRAK 6)."""
    kosong = pd.DataFrame(columns=["komponen", "jumlah"])
    if not isinstance(tgl_awal, date) or not isinstance(tgl_akhir, date) or tgl_awal > tgl_akhir:
        return kosong
    from .db import get_session
    try:
        with get_session() as s:
            return get_laporan_laba_di(s, tgl_awal, tgl_akhir)
    except Exception:
        return kosong
