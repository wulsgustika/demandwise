"""Rekomendasi harga jual dengan batas margin minimum (mock)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import mock_data as md
from . import stok_service
from .ml import musim
from .notifikasi_service import kirim_notifikasi
from .state import store, now

MARGIN_MIN = {"Makanan Pokok": 0.06}  # lainnya 10%
DEFAULT_MIN = 0.10


def margin_min(kategori: str) -> float:
    return MARGIN_MIN.get(kategori, DEFAULT_MIN)


def get_rekomendasi_harga() -> pd.DataFrame:
    """Input: HPP, tren, musim, harga pesaing.
    -> DataFrame[produk_id, nama, kategori, hpp, harga_sekarang, harga_pesaing, tren_pct, indeks_musim, margin_min, rekomendasi, margin_rek, alasan]"""
    prod = stok_service.get_produk()
    s = musim.get_penjualan_enriched(60)
    cut = pd.Timestamp(md.TODAY) - pd.Timedelta(days=30)
    now_q = s[s.tanggal > cut].groupby("produk_id").qty.sum()
    prev_q = s[s.tanggal <= cut].groupby("produk_id").qty.sum()
    tren = ((now_q / prev_q.replace(0, np.nan) - 1) * 100).fillna(0)
    idx = musim.get_indeks_musim()
    bln = musim.BULAN[md.TODAY.month % 12]  # bulan depan
    rng = np.random.default_rng(11)
    rows = []
    for r in prod.itertuples():
        pes = round(r.harga * rng.uniform(.95, 1.07), -2)
        t = float(tren.get(r.produk_id, 0))
        im = float(idx.loc[r.kategori, bln]) if r.kategori in idx.index else 1.0
        target, alasan = pes * .99, ["Mengikuti harga pesaing"]
        if t > 10 or im > 1.2:
            target *= 1.03
            alasan.append("Permintaan naik / musim ramai")
        elif t < -10:
            target *= .98
            alasan.append("Tren turun")
        mm = margin_min(r.kategori)
        lantai = r.hpp * (1 + mm)
        if target < lantai:
            target, _ = lantai, alasan.append("Dinaikkan ke batas margin minimum")
        rek = float(round(target / 100) * 100)
        rows.append(dict(produk_id=r.produk_id, nama=r.nama, kategori=r.kategori, hpp=r.hpp, harga_sekarang=r.harga,
                         harga_pesaing=float(pes), tren_pct=round(t, 1), indeks_musim=round(im, 2), margin_min=mm,
                         rekomendasi=rek, margin_rek=round((rek - r.hpp) / rek * 100, 1), alasan="; ".join(alasan)))
    return pd.DataFrame(rows)


def set_harga(produk_id: int, harga: float, alasan: str, user: str) -> dict:
    lama = store()["harga"][int(produk_id)]
    store()["harga"][int(produk_id)] = float(harga)
    nm = md.produk_df().set_index("produk_id").loc[produk_id, "nama"]
    store()["harga_log"].insert(0, dict(waktu=now(), produk=nm, lama=lama, baru=float(harga), alasan=alasan, oleh=user))
    return dict(ok=True, pesan=f"Harga {nm} diperbarui.")


def get_harga_log() -> pd.DataFrame:
    return pd.DataFrame(store()["harga_log"], columns=["waktu", "produk", "lama", "baru", "alasan", "oleh"])
