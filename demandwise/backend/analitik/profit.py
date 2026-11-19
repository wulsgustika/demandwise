"""Profit per produk, matriks kuadran (fast/slow x margin tinggi/rendah), dan tren produk."""
import numpy as np
import pandas as pd

from . import _db, data_akses as da, k
from ._util import df_aman, hari_ini

KOLOM_PROFIT = ["produk_id", "nama_produk", "kategori", "qty_terjual", "penjualan", "hpp", "laba_kotor",
                "writeoff", "laba_bersih", "margin_persen", "qty_per_hari", "kecepatan",
                "margin_level", "kuadran"]
KOLOM_TREN = ["produk_id", "nama_produk", "kategori", "qty_per_hari", "kecepatan", "qty_30_hari_terakhir",
              "qty_30_hari_sebelumnya", "perubahan_persen", "arah", "prediksi_periode_berikutnya"]

KUADRAN = {("fast", "tinggi"): "Bintang", ("fast", "rendah"): "Pendorong Omzet",
           ("slow", "tinggi"): "Niche Margin Tinggi", ("slow", "rendah"): "Evaluasi"}


def _ambang(nilai_konfig, seri: pd.Series) -> float:
    if isinstance(nilai_konfig, (int, float)):
        return float(nilai_konfig)
    s = seri.dropna()
    return float(s.median()) if len(s) else 0.0


def tabel_kecepatan(pv=None, tutup=None, h=None) -> pd.DataFrame:
    """qty/hari (hari buka) pada PERIODE_PROFIT_HARI terakhir + label fast/slow (ambang: median)."""
    if pv is None:
        pv, tutup = da.penjualan_harian_matriks()
    h = h if h is not None else hari_ini()
    prod = da.produk_aktif()
    jendela = pv.loc[(pv.index < h) & (pv.index >= h - pd.Timedelta(days=int(k.PERIODE_PROFIT_HARI)))]
    jendela = jendela.loc[~jendela.index.isin(tutup)]
    qph = jendela.mean() if len(jendela) else pd.Series(dtype=float)
    df = prod[["produk_id", "nama_produk", "kategori_id", "kategori"]].copy()
    df["qty_per_hari"] = df["produk_id"].map(qph).fillna(0.0)
    amb = _ambang(k.AMBANG_FAST, df["qty_per_hari"])
    df["kecepatan"] = np.where(df["qty_per_hari"] > amb, "fast", "slow")
    return df


@df_aman(KOLOM_PROFIT)
def get_profit_produk(tgl_awal=None, tgl_akhir=None) -> pd.DataFrame:
    """Profit bersih per produk = penjualan - HPP - write-off. Default: PERIODE_PROFIT_HARI terakhir."""
    h = hari_ini()
    akhir = pd.Timestamp(tgl_akhir) if tgl_akhir is not None else h - pd.Timedelta(days=1)
    awal = pd.Timestamp(tgl_awal) if tgl_awal is not None else akhir - pd.Timedelta(days=int(k.PERIODE_PROFIT_HARI) - 1)
    p = {"a": _db.iso(awal), "b": _db.iso(akhir)}
    jual = _db.baca("""SELECT d.produk_id, SUM(d.qty) AS qty_terjual,
                              SUM(d.qty*d.harga_satuan) AS penjualan, SUM(d.qty*d.hpp_satuan) AS hpp
                       FROM detail_penjualan d JOIN transaksi_penjualan t ON t.id = d.transaksi_id
                       WHERE t.tanggal >= :a AND t.tanggal <= :b GROUP BY d.produk_id""", p)
    wo = _db.baca("""SELECT produk_id, SUM(total_rugi) AS writeoff FROM writeoff
                     WHERE tanggal >= :a AND tanggal <= :b GROUP BY produk_id""", p)
    pv, tutup = da.penjualan_harian_matriks()
    kec = tabel_kecepatan(pv, tutup, akhir + pd.Timedelta(days=1))
    df = kec[["produk_id", "nama_produk", "kategori", "qty_per_hari", "kecepatan"]]
    df = df.merge(jual, on="produk_id", how="left").merge(wo, on="produk_id", how="left")
    for c in ["qty_terjual", "penjualan", "hpp", "writeoff"]:
        df[c] = df[c].fillna(0.0)
    df["laba_kotor"] = df["penjualan"] - df["hpp"]
    df["laba_bersih"] = df["laba_kotor"] - df["writeoff"]
    df["margin_persen"] = np.where(df["penjualan"] > 0, df["laba_bersih"] / df["penjualan"].replace(0, np.nan) * 100, np.nan)
    amb_m = _ambang(k.AMBANG_MARGIN, df.loc[df["penjualan"] > 0, "margin_persen"])
    df["margin_level"] = np.where(df["margin_persen"] > amb_m, "tinggi", "rendah")
    df["kuadran"] = [KUADRAN[(a, b)] for a, b in zip(df["kecepatan"], df["margin_level"])]
    df["margin_persen"] = df["margin_persen"].round(2)
    df["qty_per_hari"] = df["qty_per_hari"].round(2)
    for c in ["qty_terjual", "penjualan", "hpp", "laba_kotor", "writeoff", "laba_bersih"]:
        df[c] = df[c].round(0).astype("int64")
    df.attrs.update(periode_awal=str(awal.date()), periode_akhir=str(akhir.date()),
                    ambang_fast=_ambang(k.AMBANG_FAST, kec["qty_per_hari"]), ambang_margin=amb_m)
    return df[KOLOM_PROFIT].sort_values("laba_bersih", ascending=False).reset_index(drop=True)


@df_aman(KOLOM_TREN)
def get_tren_produk() -> pd.DataFrame:
    """Fast/slow-moving + arah tren (30 hari terakhir vs 30 hari sebelumnya) + prediksi 30 hari ke depan."""
    from .prediksi import prediksi_matriks
    pv, tutup = da.penjualan_harian_matriks()
    h = hari_ini()
    kec = tabel_kecepatan(pv, tutup, h)

    def total(a, b):
        w = pv.loc[(pv.index >= a) & (pv.index < b)]
        return w.sum()
    t30 = total(h - pd.Timedelta(days=30), h)
    t60 = total(h - pd.Timedelta(days=60), h - pd.Timedelta(days=30))
    pred = prediksi_matriks(h, 30, pv, tutup).sum(axis=1)
    df = kec[["produk_id", "nama_produk", "kategori", "qty_per_hari", "kecepatan"]].copy()
    df["qty_30_hari_terakhir"] = df["produk_id"].map(t30).fillna(0).round(0)
    df["qty_30_hari_sebelumnya"] = df["produk_id"].map(t60).fillna(0).round(0)
    sebelum = df["qty_30_hari_sebelumnya"].replace(0, np.nan)
    df["perubahan_persen"] = ((df["qty_30_hari_terakhir"] - sebelum) / sebelum * 100).round(1)
    df["arah"] = np.select([df["perubahan_persen"] > 10, df["perubahan_persen"] < -10], ["naik", "turun"], "stabil")
    df["prediksi_periode_berikutnya"] = df["produk_id"].map(pred).round(0)
    df["qty_per_hari"] = df["qty_per_hari"].round(2)
    return df[KOLOM_TREN].sort_values("qty_per_hari", ascending=False).reset_index(drop=True)
