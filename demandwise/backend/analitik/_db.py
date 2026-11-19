"""
Lapisan database modul analitik (Wulan).

Urutan pemilihan koneksi:
  1. engine yang sudah dipasang lewat set_engine(engine)  (dipanggil kode Naila bila perlu)
  2. engine milik proyek (backend.database / backend.db / backend.models: atribut `engine` atau `get_engine`)
  3. env DATABASE_URL atau st.secrets["DATABASE_URL"]
  4. SQLite dummy: <root>/data_dummy/demandwise_dummy.sqlite
Tabel milik fungsi ML dibuat otomatis kalau belum ada (checkfirst).
"""
import importlib
import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import (BigInteger, Boolean, Column, Date, DateTime, Float, Integer,
                        MetaData, String, Table, Text, create_engine, text)
from sqlalchemy.engine import Engine

from . import k

_engine = None
_skema_siap = False

_ROOT = Path(__file__).resolve().parents[2]
PATH_SQLITE_DUMMY = _ROOT / "data_dummy" / "demandwise_dummy.sqlite"

metadata = MetaData()

T_HASIL_PREDIKSI = Table("hasil_prediksi", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("produk_id", Integer, nullable=False, index=True),
    Column("tanggal_target", Date, nullable=False),
    Column("qty_prediksi", Float, nullable=False),
    Column("model", String(30)),
    Column("dibuat_pada", DateTime))

T_INDEKS_MUSIM = Table("indeks_musim", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("produk_id", Integer, nullable=False, index=True),
    Column("bulan", Integer, nullable=False),
    Column("indeks", Float, nullable=False))

T_EVALUASI = Table("evaluasi_model", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("produk_id", Integer, nullable=False, index=True),
    Column("model", String(30)),
    Column("versi", String(30)),
    Column("mae", Float), Column("rmse", Float), Column("mape", Float),
    Column("dievaluasi_pada", DateTime))

T_KOREKSI = Table("koreksi_prediksi", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("produk_id", Integer, nullable=False, index=True),
    Column("tanggal_target", Date, nullable=False),
    Column("qty_koreksi", Float, nullable=False),
    Column("alasan", Text),
    Column("dibuat_pada", DateTime))

T_REKOMENDASI = Table("rekomendasi_tindakan", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("batch_id", Integer, nullable=False, index=True),
    Column("jenis", String(20)),
    Column("detail", Text),
    Column("harga_diskon", BigInteger),
    Column("status", String(20)),
    Column("dibuat_pada", DateTime))

T_NOTIFIKASI = Table("notifikasi", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("jenis", String(40)),
    Column("level", String(10)),
    Column("judul", String(200)),
    Column("pesan", Text),
    Column("dibaca", Boolean, default=False),
    Column("dibuat_pada", DateTime),
    Column("ref_tabel", String(40)),
    Column("ref_id", Integer))

T_EVENT = Table("event_musiman", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nama", String(120), nullable=False),
    Column("tgl_mulai", Date, nullable=False),
    Column("tgl_selesai", Date, nullable=False),
    Column("sumber", String(10)))

_TABEL_WULAN = [T_HASIL_PREDIKSI, T_INDEKS_MUSIM, T_EVALUASI, T_KOREKSI,
                T_REKOMENDASI, T_NOTIFIKASI, T_EVENT]


def set_engine(engine: Engine):
    """Pasang engine proyek secara eksplisit (opsional)."""
    global _engine, _skema_siap
    _engine = engine
    _skema_siap = False


def _normalisasi_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def _url_dari_env():
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:  # st.secrets hanya ada kalau jalan di Streamlit
        import streamlit as st
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    return None


def _engine_proyek():
    for nama_modul in k.MODUL_ENGINE:
        try:
            mod = importlib.import_module(nama_modul)
        except Exception:
            continue
        for attr in ("engine", "get_engine"):
            obj = getattr(mod, attr, None)
            if obj is None:
                continue
            if not isinstance(obj, Engine) and callable(obj):
                try:
                    obj = obj()
                except Exception:
                    continue
            if isinstance(obj, Engine):
                return obj
    return None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        eng = _engine_proyek()
        if eng is None:
            url = _url_dari_env()
            if url:
                eng = create_engine(_normalisasi_url(url), pool_pre_ping=True)
            else:
                eng = create_engine(f"sqlite:///{PATH_SQLITE_DUMMY}")
        _engine = eng
    pastikan_skema()
    return _engine


def pastikan_skema():
    global _skema_siap
    if _skema_siap or _engine is None:
        return
    if _engine.dialect.name == "sqlite":
        _perbaiki_event_sqlite(_engine)
    metadata.create_all(_engine, tables=_TABEL_WULAN, checkfirst=True)
    _skema_siap = True


def _perbaiki_event_sqlite(eng):
    """CSV dummy membuat event_musiman tanpa primary key (id NULL saat insert).
    Bangun ulang dengan id auto increment, data lama dipertahankan."""
    with eng.begin() as conn:
        info = conn.execute(text("PRAGMA table_info(event_musiman)")).fetchall()
        if not info or any(r[5] for r in info):   # tidak ada tabel, atau sudah punya PK
            return
        conn.execute(text("ALTER TABLE event_musiman RENAME TO event_musiman_lama"))
    metadata.create_all(eng, tables=[T_EVENT], checkfirst=True)
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO event_musiman (id, nama, tgl_mulai, tgl_selesai, sumber) "
                          "SELECT id, nama, tgl_mulai, tgl_selesai, sumber FROM event_musiman_lama"))
        conn.execute(text("DROP TABLE event_musiman_lama"))


# ---------------------------------------------------------------------------
# Helper baca / tulis
# ---------------------------------------------------------------------------
def baca(sql: str, params: dict = None, tanggal=()) -> pd.DataFrame:
    """SELECT -> DataFrame. Kolom di `tanggal` diubah ke datetime64."""
    with get_engine().connect() as conn:
        df = pd.read_sql_query(text(sql), conn, params=params or {})
    for kol in tanggal:
        if kol in df.columns:
            df[kol] = pd.to_datetime(df[kol])
    return df


def jalankan(sql: str, params: dict = None):
    with get_engine().begin() as conn:
        conn.execute(text(sql), params or {})


def sisip(tabel: Table, baris: list):
    """INSERT banyak baris (list of dict). Tanggal harus date/datetime Python."""
    if not baris:
        return
    with get_engine().begin() as conn:
        conn.execute(tabel.insert(), baris)


def iso(d) -> str:
    """date/Timestamp -> 'YYYY-MM-DD' (aman untuk parameter SQL di SQLite & PostgreSQL)."""
    if isinstance(d, str):
        return d[:10]
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def sekarang() -> datetime:
    return datetime.now().replace(microsecond=0)
