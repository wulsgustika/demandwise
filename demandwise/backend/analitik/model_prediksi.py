"""
Inti model prediksi (fungsi murni, tanpa akses database).

Per produk:
  * baseline : moving average (rata-rata N hari terakhir, datar)
  * utama    : Random Forest rekursif dengan fitur lag, rata-rata bergerak, kalender
               (hari, tanggal, bulan, gajian), tren, dan event musiman
  * pemilihan model: backtest rolling-origin pada data terakhir; model dengan galat
    terkecil (konfig KRITERIA_PILIH_MODEL) dipakai untuk prediksi final.
"""
import re
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

_EPOCH = pd.Timestamp("1970-01-01")
_CAP_HARI_EVENT = 45
NAMA_MA = "moving_average"
NAMA_RF = "random_forest"


# ---------------------------------------------------------------------------
# Event & kalender
# ---------------------------------------------------------------------------
def tipe_event(nama: str) -> str:
    """'Ramadan 2026' -> 'ramadan'; 'Natal dan Tahun Baru 2025/26' -> 'natal dan tahun baru'."""
    s = re.sub(r"\d{4}(/\d{2,4})?", "", str(nama))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s or str(nama).strip().lower()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "event"


def fitur_kalender(idx: pd.DatetimeIndex, events: list) -> pd.DataFrame:
    """events: list of (nama, tgl_mulai, tgl_selesai). Fitur tidak bergantung pada nilai penjualan."""
    df = pd.DataFrame(index=idx)
    df["dow"] = idx.dayofweek
    df["dom"] = idx.day
    df["bulan"] = idx.month
    df["gajian"] = ((idx.day >= 25) | (idx.day <= 3)).astype(int)
    hari = np.array([(d - _EPOCH).days for d in idx])
    grup = {}
    for nama, m, s in events:
        grup.setdefault(_slug(tipe_event(nama)), []).append(
            ((pd.Timestamp(m) - _EPOCH).days, (pd.Timestamp(s) - _EPOCH).days))
    for sl in sorted(grup):
        mulai = np.array(sorted(a for a, _ in grup[sl]))
        selesai = np.array(sorted(b for _, b in grup[sl]))
        di_dalam = np.zeros(len(hari), dtype=bool)
        for a, b in grup[sl]:
            di_dalam |= (hari >= a) & (hari <= b)
        i = np.searchsorted(mulai, hari, side="left")
        ke = np.where(i < len(mulai), mulai[np.minimum(i, len(mulai) - 1)] - hari, _CAP_HARI_EVENT)
        j = np.searchsorted(selesai, hari, side="left") - 1
        sejak = np.where(j >= 0, hari - selesai[np.maximum(j, 0)], _CAP_HARI_EVENT)
        df[f"ev_{sl}"] = di_dalam.astype(int)
        df[f"ke_{sl}"] = np.where(di_dalam, 0, np.minimum(ke, _CAP_HARI_EVENT))
        df[f"sejak_{sl}"] = np.where(di_dalam, 0, np.minimum(sejak, _CAP_HARI_EVENT))
    return df


# ---------------------------------------------------------------------------
# Pra-pemrosesan
# ---------------------------------------------------------------------------
def siapkan_seri(serie: pd.Series, tutup: pd.DatetimeIndex):
    """Return (y_aktual dengan NaN di hari tutup, y_bersih untuk fitur/latih).
    Hari tutup toko = missing value -> diinterpolasi; lonjakan acak dipangkas."""
    y_akt = serie.astype(float).copy()
    y_akt[y_akt.index.isin(tutup)] = np.nan
    y_isi = y_akt.interpolate(limit_direction="both").fillna(0.0)
    med = y_isi.rolling(15, center=True, min_periods=5).median()
    y_bersih = np.minimum(y_isi, med * 3 + 3)
    return y_akt, y_bersih


def _fitur_lag(y: pd.Series) -> pd.DataFrame:
    g = y.shift(1)
    return pd.DataFrame({
        "lag1": y.shift(1), "lag7": y.shift(7), "lag14": y.shift(14),
        "ma7": g.rolling(7).mean(), "ma28": g.rolling(28).mean(),
        "t": np.arange(len(y), dtype=float)}, index=y.index)


def _matriks_latih(y_bersih: pd.Series, kal: pd.DataFrame, valid: np.ndarray, sampai: int,
                   koreksi: dict = None, bobot_koreksi: float = 0.5):
    """Baris latih untuk indeks < sampai. valid = bukan hari tutup."""
    lag = _fitur_lag(y_bersih)
    X = pd.concat([lag, kal.iloc[:len(y_bersih)]], axis=1).iloc[:sampai]
    y = y_bersih.iloc[:sampai].to_numpy()
    ok = (~X.isna().any(axis=1).to_numpy()) & valid[:sampai]
    cols = list(X.columns)
    Xn, yn = X.to_numpy(float)[ok], y[ok]
    w = np.ones(len(yn))
    if koreksi:
        tgl = X.index[ok]
        ekstra_x, ekstra_y = [], []
        for i, d in enumerate(tgl):
            if d in koreksi:
                ekstra_x.append(Xn[i]); ekstra_y.append(koreksi[d])
        if ekstra_x:
            Xn = np.vstack([Xn, np.array(ekstra_x)])
            yn = np.concatenate([yn, ekstra_y])
            w = np.concatenate([w, np.full(len(ekstra_y), bobot_koreksi)])
    return Xn, yn, w, cols


def _latih_rf(X, y, w, param):
    rf = RandomForestRegressor(
        n_estimators=param["rf_pohon"], min_samples_leaf=param["rf_daun"],
        max_features=0.6, random_state=42, n_jobs=1)
    rf.fit(X, y, sample_weight=w)
    return rf


def _prediksi_rekursif(model, cols, riwayat: np.ndarray, kal_depan: pd.DataFrame, t_awal: int):
    """Prediksi n hari ke depan; hasil tiap langkah dipakai sebagai lag langkah berikutnya."""
    n = len(kal_depan)
    kal_cols = cols[6:]
    kv = kal_depan[kal_cols].to_numpy(float)
    hist = list(riwayat[-28:])
    keluar = np.zeros(n)
    for i in range(n):
        lag_f = [hist[-1], hist[-7], hist[-14], float(np.mean(hist[-7:])),
                 float(np.mean(hist[-28:])), float(t_awal + i)]
        baris = np.concatenate([lag_f, kv[i]]).reshape(1, -1)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            p = max(0.0, float(model.predict(baris)[0]))
        keluar[i] = p
        hist.append(p)
    return keluar


def metrik(aktual, prediksi) -> dict:
    a = np.asarray(aktual, float)
    p = np.asarray(prediksi, float)
    if len(a) == 0:
        return {"mae": np.nan, "rmse": np.nan, "mape": np.nan}
    mae = float(np.mean(np.abs(a - p)))
    rmse = float(np.sqrt(np.mean((a - p) ** 2)))
    pos = a > 0
    mape = float(np.mean(np.abs(a[pos] - p[pos]) / a[pos]) * 100) if pos.any() else np.nan
    return {"mae": mae, "rmse": rmse, "mape": mape}


# ---------------------------------------------------------------------------
# Satu produk: backtest, pilih model, ramal
# ---------------------------------------------------------------------------
def proses_produk(pid: int, serie: pd.Series, tutup: pd.DatetimeIndex, events: list,
                  n_langkah: int, koreksi: dict, param: dict) -> dict:
    """
    serie  : qty harian (indeks tanggal harian lengkap, hari tanpa penjualan = 0)
    Prediksi dimulai sehari setelah tanggal terakhir `serie`.
    """
    y_akt, y_bersih = siapkan_seri(serie, tutup)
    n = len(serie)
    valid = ~y_akt.isna().to_numpy()
    ma_w = param["ma_window"]

    def ramal_ma(upto):
        return float(y_bersih.iloc[max(0, upto - ma_w):upto].mean()) if upto > 0 else 0.0

    idx_depan = pd.date_range(serie.index[-1] + pd.Timedelta(days=1), periods=n_langkah, freq="D")
    metrik_baris = []

    # Data terlalu pendek: moving average saja
    if n < param["rf_min_hari"]:
        h = min(param["bt_horizon"], max(0, n // 4))
        if h >= 7:
            a = y_akt.iloc[n - h:].to_numpy(); m = valid[n - h:]
            m_ma = metrik(a[m], np.full(m.sum(), ramal_ma(n - h)))
        else:
            m_ma = {"mae": np.nan, "rmse": np.nan, "mape": np.nan}
        metrik_baris.append({"model": NAMA_MA, **m_ma})
        return {"produk_id": pid, "model": NAMA_MA, "tanggal": idx_depan,
                "prediksi": np.full(n_langkah, ramal_ma(n)), "metrik": metrik_baris, "n_hari": n}

    idx_semua = serie.index.append(idx_depan)
    kal = fitur_kalender(idx_semua, events)
    kor = {pd.Timestamp(d): v for d, v in (koreksi or {}).items()}

    # --- backtest rolling-origin ---
    H, F = param["bt_horizon"], param["bt_fold"]
    origins = [n - f * H for f in range(F, 0, -1)]
    # + lipatan musiman: jendela 14 hari sebelum awal event terbaru (tiap jenis event),
    #   supaya kemampuan model menangkap musim ikut dinilai, bukan hanya periode biasa
    jenis_terpakai = set()
    for nama, m, _s in sorted(events, key=lambda e: pd.Timestamp(e[1]), reverse=True):
        if len(jenis_terpakai) >= param.get("bt_fold_event", 2):
            break
        tp = tipe_event(nama)
        o = (pd.Timestamp(m) - pd.Timedelta(days=14) - serie.index[0]).days
        if tp in jenis_terpakai or o < 120 or o + H > n - F * H:
            continue
        jenis_terpakai.add(tp)
        origins.append(o)
    akt_all, ma_all, rf_all = [], [], []
    for o in origins:
        if o < 90:
            continue
        X, y, w, cols = _matriks_latih(y_bersih, kal, valid, o)
        if len(y) < 60:
            continue
        model = _latih_rf(X, y, w, param)
        p_rf = _prediksi_rekursif(model, cols, y_bersih.iloc[:o].to_numpy(), kal.iloc[o:o + H], o)
        p_ma = np.full(H, ramal_ma(o))
        a = y_akt.iloc[o:o + H].to_numpy(); m = valid[o:o + H]
        akt_all.append(a[m]); rf_all.append(p_rf[m]); ma_all.append(p_ma[m])
    if akt_all:
        A = np.concatenate(akt_all)
        m_ma = metrik(A, np.concatenate(ma_all)); m_rf = metrik(A, np.concatenate(rf_all))
    else:
        m_ma = m_rf = {"mae": np.nan, "rmse": np.nan, "mape": np.nan}
    metrik_baris.append({"model": NAMA_MA, **m_ma})
    metrik_baris.append({"model": NAMA_RF, **m_rf})

    # --- pilih model ---
    kri = param["kriteria"]
    pilih = NAMA_RF
    if not np.isnan(m_ma[kri]) and not np.isnan(m_rf[kri]) and m_ma[kri] < m_rf[kri]:
        pilih = NAMA_MA
    elif np.isnan(m_rf[kri]):
        pilih = NAMA_MA

    # --- ramal final (latih pada seluruh data + koreksi pemilik) ---
    if pilih == NAMA_RF:
        X, y, w, cols = _matriks_latih(y_bersih, kal, valid, n, kor, param["bobot_koreksi"])
        model = _latih_rf(X, y, w, param)
        pred = _prediksi_rekursif(model, cols, y_bersih.to_numpy(), kal.iloc[n:], n)
    else:
        pred = np.full(n_langkah, ramal_ma(n))
    return {"produk_id": pid, "model": pilih, "tanggal": idx_depan, "prediksi": pred,
            "metrik": metrik_baris, "n_hari": n}
