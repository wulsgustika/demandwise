"""
backend/migrasi.py - migrasi AMAN untuk fitur multi-pengguna (SQLite lokal dan Neon PostgreSQL).

Dijalankan otomatis sekali per proses saat engine pertama dibuat (backend/db.py: get_engine),
atau manual:  python -m scripts.migrasi_multi_pengguna

Yang dilakukan (semuanya idempoten, aman diulang):
  1. users.email (sudah ada sebelumnya) dan users.akun_demo (baru).
     Akun lama tanpa email (akun dummy, mis. `pemilik`) ditandai akun_demo = TRUE.
  2. Kolom user_id (NULL, FK ke users.id) + indeks di 21 tabel data.
     Baris lama TIDAK diubah: user_id-nya tetap NULL = data demo/dummy presentasi.
  3. Keunikan produk.kode dan kategori.nama diubah dari "unik global" menjadi
     "unik per pemilik data" (agar akun A dan B boleh memakai kode/kategori yang sama).
       - PostgreSQL/Neon : buat indeks unik baru, lalu lepas CONSTRAINT unik lama (tabel & data utuh).
       - SQLite          : SQLite tidak bisa melepas constraint, jadi tabel itu disalin ke struktur
                           baru (prosedur resmi SQLite). Sebelumnya file database DICADANGKAN otomatis,
                           jumlah baris + sidik isi dicek sama persis, dan semua dalam satu transaksi
                           (gagal = dibatalkan, data tetap seperti semula).
Tidak ada TRUNCATE, DELETE, atau DROP data.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import warnings
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from .models import Base, TABEL_MILIK_PENGGUNA

log = logging.getLogger("demandwise.migrasi")
_kunci = threading.Lock()
_sudah: set = set()

# (tabel, kolom yang dulu unik global, nama indeks unik baru per pemilik)
UNIK_PER_PEMILIK = [
    ("kategori", "nama", "ux_kategori_pemilik_nama"),
    ("produk", "kode", "ux_produk_pemilik_kode"),
]


def _kunci_engine(engine: Engine) -> str:
    return engine.url.render_as_string(hide_password=True)


def pastikan_skema_multi_pengguna(engine: Engine, paksa: bool = False) -> dict:
    """Jalankan migrasi bila perlu. Return laporan langkah yang dikerjakan."""
    k = _kunci_engine(engine)
    if k in _sudah and not paksa:
        return {"langkah": [], "catatan": "sudah diperiksa di proses ini"}
    with _kunci:
        if k in _sudah and not paksa:
            return {"langkah": [], "catatan": "sudah diperiksa di proses ini"}
        laporan = _migrasi(engine)
        _sudah.add(k)
        for l in laporan["langkah"]:
            log.info("migrasi: %s", l)
        return laporan


def _migrasi(engine: Engine) -> dict:
    with warnings.catch_warnings():
        # SQLAlchemy tidak bisa merefleksi indeks berbasis ekspresi (ux_*_pemilik_*); itu memang disengaja.
        warnings.filterwarnings("ignore", message=".*expression-based index.*")
        return _migrasi_inti(engine)


def _migrasi_inti(engine: Engine) -> dict:
    langkah: list[str] = []
    insp = inspect(engine)
    if not insp.has_table("users"):
        Base.metadata.create_all(engine)       # database baru: langsung skema lengkap
        langkah.append("database baru: semua tabel dibuat")
        return {"langkah": langkah, "cadangan": None}

    pg = engine.dialect.name == "postgresql"
    cadangan = None

    # Tabel yang belum ada sama sekali dibuat (tabel yang sudah ada tidak disentuh).
    belum_ada = [t for t in Base.metadata.sorted_tables if not insp.has_table(t.name)]
    if belum_ada:
        Base.metadata.create_all(engine, tables=belum_ada)
        langkah.append("tabel baru dibuat: " + ", ".join(t.name for t in belum_ada))
        insp = inspect(engine)

    # ---- 1. kolom users ----------------------------------------------------
    kolom_users = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as c:
        if "email" not in kolom_users:
            c.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255)"))
            c.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users (email)"))
            langkah.append("kolom users.email ditambahkan")
        if "akun_demo" not in kolom_users:
            c.execute(text("ALTER TABLE users ADD COLUMN akun_demo BOOLEAN"))
            langkah.append("kolom users.akun_demo ditambahkan")
        n1 = c.execute(text("UPDATE users SET akun_demo = :v WHERE akun_demo IS NULL AND email IS NULL"),
                       {"v": True}).rowcount
        n2 = c.execute(text("UPDATE users SET akun_demo = :v WHERE akun_demo IS NULL AND email IS NOT NULL"),
                       {"v": False}).rowcount
        if n1 or n2:
            langkah.append(f"users.akun_demo diisi: {n1} akun demo, {n2} akun pengguna")

    # ---- 2. kolom user_id di tabel data -------------------------------------
    perlu_kolom = [t.name for t in TABEL_MILIK_PENGGUNA
                   if "user_id" not in {c["name"] for c in insp.get_columns(t.name)}]
    perlu_rebuild = [] if pg else [t for t, kol, _ in UNIK_PER_PEMILIK if _unik_global(insp, t, kol)]
    if not pg and (perlu_kolom or perlu_rebuild):
        cadangan = _cadangkan_sqlite(engine)
        if cadangan:
            langkah.append(f"cadangan database dibuat: {cadangan}")

    with engine.begin() as c:
        for t in perlu_kolom:
            jika = "IF NOT EXISTS " if pg else ""
            c.execute(text(f"ALTER TABLE {t} ADD COLUMN {jika}user_id INTEGER REFERENCES users(id)"))
        for t in TABEL_MILIK_PENGGUNA:
            c.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{t.name}_user_id ON {t.name} (user_id)"))
    if perlu_kolom:
        langkah.append(f"kolom user_id ditambahkan di {len(perlu_kolom)} tabel: " + ", ".join(perlu_kolom))

    # ---- 3. unik per pemilik -------------------------------------------------
    for tabel, kolom, nama_idx in UNIK_PER_PEMILIK:
        insp = inspect(engine)
        if pg:
            hasil = _unik_per_pemilik_pg(engine, insp, tabel, kolom, nama_idx)
        elif tabel in perlu_rebuild:
            hasil = _bangun_ulang_sqlite(engine, tabel)
        else:
            hasil = _pastikan_indeks(engine, tabel, nama_idx)
        if hasil:
            langkah.append(hasil)

    # ---- 4. statistik planner ------------------------------------------------
    # Tanpa statistik, planner bisa mengira indeks user_id (yang semuanya NULL pada data demo)
    # sangat selektif dan memilih rencana query yang sangat lambat. ANALYZE hanya menulis statistik.
    if langkah or not _statistik_ada(engine):
        with engine.begin() as c:
            if pg:
                for t in TABEL_MILIK_PENGGUNA:
                    c.execute(text(f"ANALYZE {t.name}"))
            else:
                c.execute(text("ANALYZE"))
        langkah.append("statistik query diperbarui (ANALYZE)")
    return {"langkah": langkah, "cadangan": cadangan}


def _statistik_ada(engine: Engine) -> bool:
    with engine.connect() as c:
        if engine.dialect.name == "postgresql":
            return c.execute(text("SELECT 1 FROM pg_stats WHERE schemaname = current_schema() "
                                  "AND attname = 'user_id' LIMIT 1")).first() is not None
        if c.execute(text("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_stat1'")).first() is None:
            return False
        return c.execute(text("SELECT 1 FROM sqlite_stat1 WHERE idx LIKE 'ix_%_user_id' LIMIT 1")).first() is not None


# ---------------------------------------------------------------------------
def _unik_global(insp, tabel: str, kolom: str) -> list[str]:
    """Nama constraint/indeks yang membuat `kolom` unik secara global (bukan per pemilik)."""
    nama = []
    for uc in insp.get_unique_constraints(tabel):
        if list(uc.get("column_names") or []) == [kolom]:
            nama.append(uc.get("name") or "(tanpa nama)")
    for ix in insp.get_indexes(tabel):
        if ix.get("unique") and list(ix.get("column_names") or []) == [kolom] \
                and not ix.get("duplicates_constraint"):
            nama.append(ix["name"])
    return nama


def _indeks_ada(engine: Engine, tabel: str, nama_idx: str) -> bool:
    """Cek langsung ke katalog (refleksi SQLAlchemy melewatkan indeks berbasis ekspresi)."""
    with engine.connect() as c:
        if engine.dialect.name == "postgresql":
            sql = ("SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() "
                   "AND tablename = :t AND indexname = :n")
        else:
            sql = "SELECT 1 FROM sqlite_master WHERE type = 'index' AND tbl_name = :t AND name = :n"
        return c.execute(text(sql), {"t": tabel, "n": nama_idx}).first() is not None


def _pastikan_indeks(engine: Engine, tabel: str, nama_idx: str) -> str | None:
    idx = next(i for i in Base.metadata.tables[tabel].indexes if i.name == nama_idx)
    if _indeks_ada(engine, tabel, nama_idx):
        return None
    with engine.begin() as c:
        c.execute(CreateIndex(idx, if_not_exists=True))
    return f"indeks {nama_idx} dibuat"


def _unik_per_pemilik_pg(engine: Engine, insp, tabel: str, kolom: str, nama_idx: str) -> str | None:
    lama_uc = [u["name"] for u in insp.get_unique_constraints(tabel)
               if list(u.get("column_names") or []) == [kolom] and u.get("name")]
    lama_ix = [i["name"] for i in insp.get_indexes(tabel)
               if i.get("unique") and list(i.get("column_names") or []) == [kolom]
               and not i.get("duplicates_constraint") and i["name"] not in lama_uc]
    sudah = _indeks_ada(engine, tabel, nama_idx)
    if sudah and not lama_uc and not lama_ix:
        return None
    idx = next(i for i in Base.metadata.tables[tabel].indexes if i.name == nama_idx)
    with engine.begin() as c:            # satu transaksi: indeks baru dulu, baru lepas yang lama
        c.execute(CreateIndex(idx, if_not_exists=True))
        for n in lama_uc:
            c.execute(text(f'ALTER TABLE {tabel} DROP CONSTRAINT IF EXISTS "{n}"'))
        for n in lama_ix:
            c.execute(text(f'DROP INDEX IF EXISTS "{n}"'))
    return (f"{tabel}.{kolom}: unik per pemilik ({nama_idx})"
            + (f", constraint unik global dilepas: {', '.join(lama_uc + lama_ix)}" if lama_uc or lama_ix else ""))


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
def _path_sqlite(engine: Engine) -> Path | None:
    db = engine.url.database
    if not db or db == ":memory:":
        return None
    return Path(db)


def _cadangkan_sqlite(engine: Engine) -> str | None:
    """Salin utuh file SQLite memakai backup API SQLite (aman walau koneksi lain terbuka)."""
    path = _path_sqlite(engine)
    if path is None or not path.exists():
        return None
    import sqlite3
    tujuan = path.with_name(f"{path.stem}.cadangan-{datetime.now():%Y%m%d-%H%M%S}{path.suffix}")
    src = sqlite3.connect(str(path))
    dst = sqlite3.connect(str(tujuan))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return str(tujuan)


def _sidik(cur, tabel: str, kolom: list[str]) -> tuple[int, str]:
    h = hashlib.sha256()
    n = 0
    daftar = ", ".join(f'"{k}"' for k in kolom)
    for baris in cur.execute(f'SELECT {daftar} FROM "{tabel}" ORDER BY id'):
        h.update(repr(baris).encode())
        n += 1
    return n, h.hexdigest()


def _bangun_ulang_sqlite(engine: Engine, tabel: str) -> str:
    """Prosedur resmi SQLite (https://sqlite.org/lang_altertable.html#otheralter):
    buat tabel baru berstruktur benar -> salin semua baris -> cek sama persis -> ganti nama.
    Semua dalam satu transaksi; bila ada yang tidak cocok, ROLLBACK dan data lama tetap."""
    t = Base.metadata.tables[tabel]
    sementara = f"{tabel}__baru"
    raw = engine.raw_connection()
    try:
        con = raw.driver_connection
        iso_lama = con.isolation_level
        con.isolation_level = None          # kendali transaksi manual
        cur = con.cursor()
        cur.execute("PRAGMA foreign_keys=OFF")
        try:
            cur.execute("BEGIN IMMEDIATE")
            kolom_lama = [r[1] for r in cur.execute(f'PRAGMA table_info("{tabel}")')]
            kolom_model = [c.name for c in t.columns]
            asing = [k for k in kolom_lama if k not in kolom_model]
            if asing:
                raise RuntimeError(f"tabel {tabel} punya kolom di luar models.py ({asing}); migrasi dibatalkan")
            fk_sebelum = set(map(tuple, cur.execute("PRAGMA foreign_key_check").fetchall()))
            n_lama, sidik_lama = _sidik(cur, tabel, kolom_lama)

            ddl = str(CreateTable(t).compile(engine)).strip()
            awalan = f"CREATE TABLE {tabel} ("
            if not ddl.startswith(awalan):
                raise RuntimeError(f"DDL {tabel} tidak dikenali")
            cur.execute(f"CREATE TABLE {sementara} (" + ddl[len(awalan):])
            daftar = ", ".join(f'"{k}"' for k in kolom_lama)
            cur.execute(f'INSERT INTO {sementara} ({daftar}) SELECT {daftar} FROM "{tabel}"')
            n_baru, sidik_baru = _sidik(cur, sementara, kolom_lama)
            if (n_baru, sidik_baru) != (n_lama, sidik_lama):
                raise RuntimeError(f"salinan {tabel} tidak sama persis ({n_lama} vs {n_baru} baris)")

            cur.execute(f'DROP TABLE "{tabel}"')            # tabel lama, isinya sudah tersalin & terverifikasi
            cur.execute(f'ALTER TABLE {sementara} RENAME TO "{tabel}"')
            for idx in t.indexes:
                cur.execute(str(CreateIndex(idx, if_not_exists=True).compile(engine)))

            n_akhir, sidik_akhir = _sidik(cur, tabel, kolom_lama)
            fk_sesudah = set(map(tuple, cur.execute("PRAGMA foreign_key_check").fetchall()))
            if (n_akhir, sidik_akhir) != (n_lama, sidik_lama) or not fk_sesudah <= fk_sebelum:
                raise RuntimeError(f"verifikasi akhir {tabel} gagal")
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        finally:
            cur.execute("PRAGMA foreign_keys=ON")
            con.isolation_level = iso_lama
    finally:
        raw.close()
    return (f"{tabel}: unik per pemilik (SQLite, {n_lama} baris disalin ke struktur baru, "
            "jumlah & isi terverifikasi sama persis)")
