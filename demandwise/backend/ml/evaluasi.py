"""Evaluasi model (MAE, RMSE, MAPE) & retraining (mock)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import mock_data as md
from ..state import store, now
from . import prediksi


def get_riwayat_retrain() -> pd.DataFrame:
    return pd.DataFrame(store()["retrain"])


def get_evaluasi_produk() -> pd.DataFrame:
    """-> DataFrame[nama, kategori, mae, rmse, mape] (backtest 28 hari terakhir, mock)."""
    sales = md.penjualan_harian_df()
    prod = md.produk_df()
    rng = np.random.default_rng(7)
    ver = get_riwayat_retrain().iloc[-1]
    skala = float(ver.mape) / 12.9
    rows = []
    for r in prod.itertuples():
        a = sales[sales.produk_id == r.produk_id].sort_values("tanggal").tail(28).qty.values.astype(float)
        err = (a - np.convolve(np.pad(a, (6, 0), mode="edge"), np.ones(7) / 7, mode="valid")) * rng.uniform(.6, .9) * skala
        rows.append(dict(nama=r.nama, kategori=r.kategori, mae=float(np.abs(err).mean()), rmse=float(np.sqrt((err ** 2).mean())),
                         mape=float(np.abs(err / np.maximum(a, 1)).mean() * 100)))
    return pd.DataFrame(rows)


def jalankan_retrain(user: str) -> dict:
    """Retrain memakai koreksi manual sebagai data latih; simpan versi baru (joblib pada versi final)."""
    rt = store()["retrain"]
    last = rt[-1]
    n_kor = len(store()["koreksi"])
    ver = f"v1.{len(rt)}"
    rt.append(dict(versi=ver, tanggal=md.TODAY.isoformat(), algoritma=last["algoritma"],
                   mae=round(last["mae"] * .96, 2), rmse=round(last["rmse"] * .96, 2), mape=round(last["mape"] * .95, 1),
                   data_latih=last["data_latih"] + 380 + n_kor, catatan=f"Retrain oleh {user}; {n_kor} koreksi manual dipakai"))
    return dict(ok=True, pesan=f"Retraining selesai. Model {ver} aktif.", versi=ver)
