"""Laporan HPP & laba, biaya operasional, verifikasi laporan, KPI dashboard (mock)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from . import mock_data as md
from . import stok_service
from .ml import musim
from .notifikasi_service import kirim_notifikasi
from .state import store, now, next_id


def daftar_periode() -> list[str]:
    s = md.penjualan_harian_df()
    return sorted(s.tanggal.dt.strftime("%Y-%m").unique(), reverse=True)


def simpan_biaya(kategori: str, tanggal: date, jumlah: float, keterangan: str, user: str) -> dict:
    store()["biaya"].insert(0, dict(id=next_id("biaya"), tanggal=tanggal, kategori=kategori, jumlah=float(jumlah), keterangan=keterangan, oleh=user))
    return dict(ok=True, pesan=f"Biaya {kategori} sebesar Rp {jumlah:,.0f} tersimpan.".replace(",", "."))


def get_biaya() -> pd.DataFrame:
    b = pd.DataFrame(store()["biaya"])
    b["tanggal"] = pd.to_datetime(b.tanggal)
    return b.sort_values("tanggal", ascending=False).reset_index(drop=True)


def get_laporan_laba(periode: str) -> dict:
    """-> dict(ringkasan{omzet,hpp,laba_kotor,writeoff,biaya,laba_bersih}, produk DataFrame)"""
    s = musim.get_penjualan_enriched()
    s = s[s.tanggal.dt.strftime("%Y-%m") == periode]
    baru = pd.DataFrame(store()["penjualan_baru"])
    g = s.groupby(["produk_id", "nama", "kategori"]).agg(qty=("qty", "sum"), omzet=("omzet", "sum"), hpp=("biaya_pokok", "sum")).reset_index()
    if len(baru) and periode == md.TODAY.strftime("%Y-%m"):
        b = baru.groupby("produk_id").agg(qty=("qty", "sum"), omzet=("nilai", "sum"), hpp=("hpp", "sum"))
        g = g.set_index("produk_id")
        for pid, r in b.iterrows():
            g.loc[pid, ["qty", "omzet", "hpp"]] += r[["qty", "omzet", "hpp"]].values
        g = g.reset_index()
    g["laba_kotor"] = g.omzet - g.hpp
    wo = stok_service.get_writeoff()
    wo = wo[pd.to_datetime(wo.tanggal).dt.strftime("%Y-%m") == periode] if len(wo) else wo
    bi = get_biaya()
    bi = bi[bi.tanggal.dt.strftime("%Y-%m") == periode]
    r = dict(omzet=float(g.omzet.sum()), hpp=float(g.hpp.sum()), writeoff=float(wo.nilai.sum()) if len(wo) else 0.0, biaya=float(bi.jumlah.sum()))
    r["laba_kotor"] = r["omzet"] - r["hpp"]
    r["laba_bersih"] = r["laba_kotor"] - r["writeoff"] - r["biaya"]
    return dict(ringkasan=r, produk=g.sort_values("laba_kotor", ascending=False).reset_index(drop=True), biaya=bi, writeoff=wo)


def get_status_laporan(periode: str) -> dict:
    return store()["laporan_status"].get(periode, dict(status="Menunggu Verifikasi", oleh="-", waktu="-", catatan=""))


def verifikasi_laporan(periode: str, user: str, catatan: str = "") -> dict:
    store()["laporan_status"][periode] = dict(status="Terverifikasi", oleh=user, waktu=now(), catatan=catatan)
    kirim_notifikasi("Pemilik", "Laporan", f"Laporan laba {periode} telah diverifikasi Manajer ({user}).")
    return dict(ok=True, pesan=f"Laporan {periode} terverifikasi dan dikirim ke Pemilik.")


def batalkan_verifikasi(periode: str) -> None:
    store()["laporan_status"].pop(periode, None)


def get_kpi_dashboard() -> dict:
    s = musim.get_penjualan_enriched(60)
    cut = pd.Timestamp(md.TODAY) - pd.Timedelta(days=29)
    cur, prev = s[s.tanggal >= cut], s[s.tanggal < cut]
    st_ = stok_service.get_stok_status()
    per = (pd.Timestamp(md.TODAY).replace(day=1) - pd.Timedelta(days=1)).strftime("%Y-%m")  # bulan lalu (penuh)
    lap = get_laporan_laba(per)["ringkasan"]
    from .ml import expiry
    rk = expiry.get_risiko_kedaluwarsa()
    return dict(
        nilai_stok=float(st_.nilai_stok.sum()), omzet_30=float(cur.omzet.sum()), omzet_prev=float(prev.omzet.sum()),
        laba_bulan=lap["laba_bersih"], periode=per, menipis=int((st_.status == "Menipis").sum()), overstock=int((st_.status == "Overstock").sum()),
        kritis=int(((rk.level == "Kritis") & (rk.berisiko > 0)).sum()), siaga=int(((rk.level == "Siaga") & (rk.berisiko > 0)).sum()),
        waspada=int(((rk.level == "Waspada") & (rk.berisiko > 0)).sum()), nilai_risiko=float(rk.nilai_risiko.sum()),
    )
