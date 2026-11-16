"""Indeks musim, event musiman, profit & matriks fast/slow x margin (mock)."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .. import mock_data as md
from .. import stok_service
from ..notifikasi_service import kirim_notifikasi
from ..state import store, next_id

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def get_penjualan_enriched(hari: int | None = None) -> pd.DataFrame:
    s = md.penjualan_harian_df()
    if hari:
        s = s[s.tanggal >= pd.Timestamp(md.TODAY) - pd.Timedelta(days=hari - 1)]
    p = stok_service.get_produk()[["produk_id", "nama", "kategori", "hpp", "harga"]]
    s = s.merge(p, on="produk_id")
    s["omzet"] = s.qty * s.harga
    s["biaya_pokok"] = s.qty * s.hpp
    return s


def get_indeks_musim() -> pd.DataFrame:
    """Indeks musim = rata-rata penjualan harian bulan tsb / rata-rata seluruh bulan.
    -> DataFrame index=kategori (+ 'Semua'), kolom=Jan..Des"""
    s = get_penjualan_enriched()
    s["bulan"] = s.tanggal.dt.month
    out = {}
    for kat, g in list(s.groupby("kategori")) + [("Semua", s)]:
        harian = g.groupby("tanggal").agg(qty=("qty", "sum")).reset_index()
        harian["bulan"] = harian.tanggal.dt.month
        m = harian.groupby("bulan").qty.mean()
        out[kat] = (m / m.mean()).reindex(range(1, 13))
    df = pd.DataFrame(out).T
    df.columns = BULAN
    return df.round(2)


def get_tren_bulanan() -> pd.DataFrame:
    s = get_penjualan_enriched()
    s["periode"] = s.tanggal.dt.to_period("M").dt.to_timestamp()
    return s.groupby(["periode", "kategori"]).agg(qty=("qty", "sum"), omzet=("omzet", "sum")).reset_index()


def get_profit_produk(hari: int = 90) -> pd.DataFrame:
    """-> DataFrame[produk_id, nama, kategori, qty, omzet, laba_kotor, writeoff, laba_bersih, margin_pct, qty_per_hari, kuadran]"""
    s = get_penjualan_enriched(hari)
    g = s.groupby(["produk_id", "nama", "kategori"]).agg(qty=("qty", "sum"), omzet=("omzet", "sum"), hpp_total=("biaya_pokok", "sum")).reset_index()
    wo = stok_service.get_writeoff()
    if len(wo):
        wo = wo[pd.to_datetime(wo.tanggal) >= pd.Timestamp(md.TODAY) - pd.Timedelta(days=hari)]
        g["writeoff"] = g.produk_id.map(wo.groupby("produk_id").nilai.sum()).fillna(0.0)
    else:
        g["writeoff"] = 0.0
    g["laba_kotor"] = g.omzet - g.hpp_total
    g["laba_bersih"] = g.laba_kotor - g.writeoff
    g["margin_pct"] = (g.laba_kotor / g.omzet * 100).round(1)
    g["qty_per_hari"] = (g.qty / hari).round(2)
    fast = g.qty_per_hari >= g.qty_per_hari.median()
    hi = g.margin_pct >= 22
    g["kecepatan"] = np.where(fast, "Fast", "Slow")
    g["margin_level"] = np.where(hi, "Tinggi", "Rendah")
    g["kuadran"] = np.select([fast & hi, fast & ~hi, ~fast & hi], ["Bintang (Fast + Margin tinggi)", "Volume (Fast + Margin rendah)",
                                                                   "Niche untung (Slow + Margin tinggi)"], "Tinjau ulang (Slow + Margin rendah)")
    return g.sort_values("laba_bersih", ascending=False).reset_index(drop=True)


def get_event_musiman() -> pd.DataFrame:
    e = store()["event"].copy()
    e["h_minus"] = e.mulai.map(lambda d: (d - md.TODAY).days)
    return e


def simpan_event(nama: str, mulai: date, selesai: date, kategori: list[str], lonjakan: float, user: str) -> dict:
    e = store()["event"]
    store()["event"] = pd.concat([e, pd.DataFrame([dict(event_id=int(e.event_id.max()) + 1, nama=nama, mulai=mulai, selesai=selesai,
                                                         kategori=", ".join(kategori), lonjakan=lonjakan, status="Terkonfirmasi")])], ignore_index=True)
    kirim_notifikasi("Semua", "Musim", f"Event musiman baru: {nama} ({mulai:%d %b %Y}).")
    return dict(ok=True, pesan=f"Event '{nama}' ditambahkan dan terkonfirmasi.")


def konfirmasi_event(event_id: int) -> None:
    e = store()["event"]
    e.loc[e.event_id == event_id, "status"] = "Terkonfirmasi"
    nm = e.loc[e.event_id == event_id, "nama"].iloc[0]
    kirim_notifikasi("Staf Pembelian", "Musim", f"Event '{nm}' terkonfirmasi. Siapkan stok musiman (dibatasi masa simpan).")


def get_trigger_musiman() -> pd.DataFrame:
    """Event dengan H-30 (atau kurang) dan indeks musim > 1,2 -> pemicu persiapan stok musiman."""
    e = get_event_musiman()
    return e[(e.h_minus <= 30) & (e.h_minus >= -3) & (e.lonjakan > 1.2)]
