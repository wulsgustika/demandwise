"""
db.py - koneksi database (pemilik: Naila).

Urutan pencarian alamat database:
1. Variabel lingkungan DEMANDWISE_DB_URL  (untuk skrip dan tes)
2. st.secrets["database"]["url"]          (untuk aplikasi Streamlit / Neon)
3. SQLite lokal: demandwise.sqlite di folder proyek

Contoh .streamlit/secrets.toml (JANGAN di-commit):
    [database]
    url = "postgresql://USER:PASSWORD@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
"""
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

SQLITE_DEFAULT = Path(__file__).resolve().parent.parent / "demandwise.sqlite"

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _normalisasi(url: str) -> str:
    """Neon/Supabase kadang memberi 'postgres://'; SQLAlchemy butuh driver eksplisit."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def ambil_url() -> str:
    url = os.environ.get("DEMANDWISE_DB_URL")
    if url:
        return _normalisasi(url)
    try:
        import streamlit as st
        url = st.secrets["database"]["url"]
        if url:
            return _normalisasi(url)
    except Exception:
        pass  # tidak ada streamlit / tidak ada secrets -> pakai SQLite
    return f"sqlite:///{SQLITE_DEFAULT}"


def buat_engine(url: str | None = None) -> Engine:
    url = _normalisasi(url) if url else ambil_url()
    if url.startswith("sqlite"):
        engine = create_engine(url, future=True)

        @event.listens_for(engine, "connect")
        def _aktifkan_fk(dbapi_conn, _):
            # SQLite mengabaikan FOREIGN KEY kecuali diaktifkan per koneksi.
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine
    # pool_pre_ping: Neon menidurkan koneksi saat sepi; cek dulu sebelum dipakai.
    return create_engine(url, pool_pre_ping=True, pool_recycle=300, future=True)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = buat_engine()
    return _engine


def get_session() -> Session:
    """Pemakaian:  with get_session() as s: ... ; s.commit()"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal()


def buat_semua_tabel(engine: Engine | None = None) -> None:
    Base.metadata.create_all(engine or get_engine())
