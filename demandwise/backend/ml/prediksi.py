"""Prediksi permintaan (mock: baseline deseasonalized moving average).
Naila: ganti isi `_forecast_all` dengan model ML; signature fungsi publik tetap."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from .. import mock_data as md
from ..state import store, now, next_id

HORIZON_MAX = 90


@st.cache_data(show_spinner=False)
def _forecast_all() -> pd.DataFrame:
    sales = md.penjualan_harian_df()
    prod = md.produk_df()
    fut = pd.date_range(pd.Timestamp(md.TODAY) + pd.Timedelta(days=1), periods=HORIZON_MAX, freq="D")
    out = []
    for r in prod.itertuples():
        h = sales[sales.produk_id == r.produk_id].sort_values("tanggal")
        last = h.tail(28)
        li = pd.DatetimeIndex(last.tanggal)
        norm = md.musim_factor(r.tag, li) * md._dow(li)
        base = float((last.qty.values / norm).mean())
        yhat = base * md.musim_factor(r.tag, fut) * md._dow(fut)
        sigma = np.sqrt(np.maximum(yhat, .5)) * 1.25
        out.append(pd.DataFrame({
            "produk_id": r.produk_id, "tanggal": fut, "yhat": yhat,
            "lower": np.maximum(0, yhat - 1.28 * sigma), "upper": yhat + 1.28 * sigma,
        }))
    return pd.concat(out, ignore_index=True)


def get_prediksi(produk_id: int | None = None, horizon: int = 30, dengan_koreksi: bool = True) -> pd.DataFrame:
    """-> DataFrame[produk_id, tanggal, yhat, lower, upper, koreksi]"""
    df = _forecast_all()
    df = df[df.tanggal <= pd.Timestamp(md.TODAY) + pd.Timedelta(days=horizon)].copy()
    if produk_id is not None:
        df = df[df.produk_id == produk_id].copy()
    df["koreksi"] = np.nan
    if dengan_koreksi:
        for k in store()["koreksi"]:
            m = (df.produk_id == k["produk_id"]) & (df.tanggal == pd.Timestamp(k["tanggal"]))
            df.loc[m, "koreksi"] = k["nilai"]
            df.loc[m, "yhat"] = k["nilai"]
    return df.reset_index(drop=True)


def get_riwayat(produk_id: int, hari: int = 90) -> pd.DataFrame:
    """-> DataFrame[tanggal, qty]"""
    h = md.penjualan_harian_df()
    h = h[h.produk_id == produk_id].sort_values("tanggal").tail(hari)
    return h[["tanggal", "qty"]].reset_index(drop=True)


def simpan_koreksi(produk_id: int, tanggal, nilai: float, alasan: str, user: str) -> dict:
    s = store()
    kid = next_id("koreksi")
    asli = get_prediksi(produk_id, HORIZON_MAX, dengan_koreksi=False)
    asli = asli[asli.tanggal == pd.Timestamp(tanggal)]
    s["koreksi"].append(dict(id=kid, produk_id=produk_id, tanggal=pd.Timestamp(tanggal).date(), nilai=float(nilai),
                             prediksi_model=float(asli.yhat.iloc[0]) if len(asli) else None,
                             alasan=alasan, oleh=user, waktu=now(), dipakai_latih=True))
    return dict(ok=True, pesan="Koreksi disimpan dan akan dipakai sebagai data latih pada retraining berikutnya.")


def hapus_koreksi(koreksi_id: int) -> None:
    s = store()
    s["koreksi"] = [k for k in s["koreksi"] if k["id"] != koreksi_id]


def get_koreksi() -> pd.DataFrame:
    rows = store()["koreksi"]
    if not rows:
        return pd.DataFrame(columns=["id", "produk_id", "tanggal", "nilai", "prediksi_model", "alasan", "oleh", "waktu", "dipakai_latih"])
    return pd.DataFrame(rows)
