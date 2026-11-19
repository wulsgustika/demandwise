"""Status stok: safety stock, reorder point, menipis / aman / overstock."""
import math

import numpy as np
import pandas as pd

from . import data_akses as da, k
from ._util import df_aman, hari_ini
from .prediksi import prediksi_matriks

KOLOM_STOK = ["produk_id", "nama_produk", "stok_saat_ini", "prediksi_demand_lead_time", "safety_stock",
              "reorder_point", "status", "selisih_dari_rop"]


def stok_sekarang(h) -> pd.Series:
    """Stok layak jual per produk: batch aktif yang belum lewat tanggal kedaluwarsa."""
    b = da.batch_aktif()
    b = b[b["tgl_kedaluwarsa"] >= h]
    return b.groupby("produk_id")["jumlah_sisa"].sum()


def hitung_stok_status(h=None) -> pd.DataFrame:
    h = h if h is not None else hari_ini()
    prod = da.produk_aktif()
    pv, tutup = da.penjualan_harian_matriks()
    n = int(max(k.OVERSTOCK_HORIZON_HARI, prod["lead_time_hari"].max()))
    pred = prediksi_matriks(h, n, pv, tutup)
    stok = stok_sekarang(h)
    jendela = pv.loc[(pv.index < h)].tail(int(k.JENDELA_SIGMA_HARI))
    jendela = jendela.loc[~jendela.index.isin(tutup)]
    sigma = jendela.std(ddof=1)
    baris = []
    for p in prod.itertuples():
        lt = int(p.lead_time_hari)
        pr = pred.loc[p.produk_id].to_numpy()
        dem_lt = float(pr[:lt].sum())
        dem_h = float(pr[:int(k.OVERSTOCK_HORIZON_HARI)].sum())
        sg = float(sigma.get(p.produk_id, 0.0)) if p.produk_id in sigma.index else 0.0
        sg = 0.0 if np.isnan(sg) else sg
        ss = math.ceil(k.Z_SAFETY_STOCK * sg * math.sqrt(lt))
        rop = dem_lt + ss                      # = prediksi_harian x lead_time + safety_stock
        st = float(stok.get(p.produk_id, 0))
        status = "menipis" if st <= rop else ("overstock" if st > rop + dem_h else "aman")
        baris.append({"produk_id": p.produk_id, "nama_produk": p.nama_produk,
                      "stok_saat_ini": int(st), "prediksi_demand_lead_time": round(dem_lt, 1),
                      "safety_stock": int(ss), "reorder_point": round(rop, 1), "status": status,
                      "selisih_dari_rop": round(st - rop, 1)})
    return pd.DataFrame(baris, columns=KOLOM_STOK)


@df_aman(KOLOM_STOK)
def get_stok_status() -> pd.DataFrame:
    """Urut dari yang paling mendesak (selisih_dari_rop terkecil)."""
    df = hitung_stok_status()
    return df.sort_values("selisih_dari_rop").reset_index(drop=True)
