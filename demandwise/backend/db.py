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
import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria

from .konteks import ruang_aktif
from .models import Base, MilikPengguna

log = logging.getLogger("demandwise.db")

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
        eng = buat_engine()
        # Migrasi aman multi-pengguna (hanya MENAMBAH kolom/indeks, tidak menghapus data).
        from .migrasi import pastikan_skema_multi_pengguna
        pastikan_skema_multi_pengguna(eng)
        _engine = eng
    return _engine


def get_session() -> Session:
    """Pemakaian:  with get_session() as s: ... ; s.commit()"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal()


def buat_semua_tabel(engine: Engine | None = None) -> None:
    Base.metadata.create_all(engine or get_engine())


def pastikan_kolom_email(engine: Engine | None = None) -> None:
    """Migrasi ringan: tambahkan kolom users.email + indeks unik bila database lama belum punya.

    create_all() tidak mengubah tabel yang sudah ada, jadi SQLite/Neon lama perlu ALTER TABLE.
    Aman dipanggil berulang kali (tidak berbuat apa-apa bila kolom sudah ada).
    """
    from sqlalchemy import inspect, text
    engine = engine or get_engine()
    insp = inspect(engine)
    if not insp.has_table("users"):
        Base.metadata.create_all(engine)
        return
    kolom = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as c:
        if "email" not in kolom:
            c.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255)"))
            # Indeks unik: banyak NULL (akun lama) tetap diizinkan di SQLite maupun PostgreSQL.
            c.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users (email)"))


# ---------------------------------------------------------------------------
# Pemisahan data per pengguna (lihat backend/konteks.py)
# ---------------------------------------------------------------------------
@event.listens_for(Session, "do_orm_execute")
def _saring_milik_pengguna(state) -> None:
    """Setiap SELECT/UPDATE/DELETE ORM otomatis dibatasi ke data ruang aktif:
    akun demo -> user_id IS NULL (data dummy), akun pengguna -> user_id = id akunnya."""
    if not (state.is_select or state.is_update or state.is_delete):
        return
    if state.is_select and (state.is_column_load or state.is_relationship_load):
        return
    ruang = ruang_aktif()
    if ruang.demo:
        kriteria = with_loader_criteria(MilikPengguna, lambda cls: cls.user_id.is_(None),
                                        include_aliases=True)
    else:
        uid = ruang.user_id
        kriteria = with_loader_criteria(MilikPengguna, lambda cls: cls.user_id == uid,
                                        include_aliases=True)
    state.statement = state.statement.options(kriteria)


@event.listens_for(Session, "before_flush")
def _isi_pemilik_data(session, _ctx, _instances) -> None:
    """Baris baru otomatis diberi user_id akun yang login; baris milik orang lain tidak boleh diubah."""
    ruang = ruang_aktif()
    for obj in session.new:
        if isinstance(obj, MilikPengguna):
            if ruang.terkunci:
                raise PermissionError("Silakan masuk (login) terlebih dahulu.")
            if not ruang.demo and obj.user_id is None:
                obj.user_id = ruang.user_id
    for obj in list(session.dirty) + list(session.deleted):
        if isinstance(obj, MilikPengguna) and obj.user_id != ruang.user_id:
            raise PermissionError("Data ini bukan milik akun Anda.")
