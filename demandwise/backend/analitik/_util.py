"""Utilitas umum: pembungkus aman, tanggal acuan, format."""
import functools
import logging
from datetime import date, timedelta

import pandas as pd

from . import _db, k

log = logging.getLogger("demandwise.analitik")


def hasil(ok: bool, pesan: str, data=None) -> dict:
    return {"ok": ok, "pesan": pesan, "data": data}


def aksi_aman(fn):
    """Fungsi aksi: tidak pernah melempar exception, selalu return dict baku."""
    @functools.wraps(fn)
    def bungkus(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:  # noqa
            log.exception("Gagal di %s", fn.__name__)
            if k.RAISE_ERROR:
                raise
            return hasil(False, f"Terjadi kesalahan di {fn.__name__}: {e}", None)
    return bungkus


def df_aman(kolom):
    """Fungsi DataFrame: kalau gagal, log error dan return DataFrame kosong berkolom benar."""
    def deko(fn):
        @functools.wraps(fn)
        def bungkus(*a, **kw):
            try:
                return fn(*a, **kw)
            except Exception:
                log.exception("Gagal di %s", fn.__name__)
                if k.RAISE_ERROR:
                    raise
                return pd.DataFrame(columns=kolom)
        return bungkus
    return deko


def dict_aman(default_fn):
    def deko(fn):
        @functools.wraps(fn)
        def bungkus(*a, **kw):
            try:
                return fn(*a, **kw)
            except Exception:
                log.exception("Gagal di %s", fn.__name__)
                if k.RAISE_ERROR:
                    raise
                return default_fn()
        return bungkus
    return deko


def hari_ini() -> pd.Timestamp:
    """Tanggal acuan 'hari ini' (lihat konfig MODE_TANGGAL)."""
    import os
    manual = os.environ.get("DEMANDWISE_HARI_INI")  # untuk demo/uji, format YYYY-MM-DD
    if manual:
        return pd.Timestamp(manual).normalize()
    mode = os.environ.get("DEMANDWISE_MODE_TANGGAL", k.MODE_TANGGAL)
    if mode == "sistem":
        return pd.Timestamp(date.today())
    df = _db.baca("SELECT MAX(tanggal) AS t FROM transaksi_penjualan")
    t = df["t"].iloc[0] if len(df) else None
    if t is None or pd.isna(t):
        return pd.Timestamp(date.today())
    return pd.Timestamp(t).normalize() + timedelta(days=1)


def tgl_id(d) -> str:
    """Format tampil DD-MM-YYYY (untuk teks pesan)."""
    return pd.Timestamp(d).strftime("%d-%m-%Y")


def rp(x) -> str:
    """Rp 1.250.000"""
    return "Rp " + f"{int(round(float(x))):,}".replace(",", ".")
