"""
muat_ke_postgres.py - jembatan dari file CSV ke database (pemilik: Naila).

Yang dikerjakan:
1. Membaca CSV data dummy buatan Wulan (16 file) dari --folder.
2. Membuat tabel kalau belum ada (dari backend/models.py).
3. Mengosongkan tabel kalau sudah ada isinya (--kosongkan atau --reset).
4. Memasukkan semua baris, berurutan supaya relasi antar tabel aman.
5. Mencetak jumlah baris tiap tabel untuk dicek.

Pemakaian (dari folder proyek):
    # Neon / PostgreSQL (alamat dari .streamlit/secrets.toml atau variabel lingkungan):
    export DEMANDWISE_DB_URL="postgresql://USER:PASS@host/db?sslmode=require"   (Mac/Linux)
    set DEMANDWISE_DB_URL=postgresql://USER:PASS@host/db?sslmode=require        (Windows)
    python -m scripts.muat_ke_postgres --folder data_dummy

    # Kalau tabel sudah berisi dan mau diisi ulang (struktur tabel dipertahankan):
    python -m scripts.muat_ke_postgres --folder data_dummy --kosongkan

    # Kalau models.py berubah dan tabel harus dibangun ulang (tabel dihapus lalu dibuat):
    python -m scripts.muat_ke_postgres --folder data_dummy --reset

Tanpa --db-url, alamat dibaca seperti di backend/db.py; tanpa secrets/variabel
lingkungan skrip memakai SQLite lokal (demandwise.sqlite).
Cukup dijalankan sekali; boleh diulang untuk reset.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, BigInteger, text
from sqlalchemy.engine import Engine

from backend.db import buat_engine
from backend.models import Base, URUTAN_TABEL

PASSWORD_DEMO = "demo123"
CHUNK = 5000


def _hash_demo() -> str:
    try:
        import bcrypt
    except ImportError:
        sys.exit("Butuh bcrypt:  pip install bcrypt")
    return bcrypt.hashpw(PASSWORD_DEMO.encode(), bcrypt.gensalt()).decode()


def _siapkan(df: pd.DataFrame, tabel) -> list[dict]:
    """Ubah DataFrame CSV jadi daftar dict dengan tipe Python yang sesuai kolom."""
    df = df[[c.name for c in tabel.columns if c.name in df.columns]].copy()
    for kolom in tabel.columns:
        if kolom.name not in df.columns:
            continue
        s, tipe = df[kolom.name], kolom.type
        if isinstance(tipe, Date):
            df[kolom.name] = pd.to_datetime(s).dt.date
        elif isinstance(tipe, DateTime):
            df[kolom.name] = pd.to_datetime(s).dt.to_pydatetime()
        elif isinstance(tipe, Boolean):
            df[kolom.name] = s.map(lambda v: str(v).strip().lower() in ("true", "1", "t", "ya"))
        elif isinstance(tipe, (Integer, BigInteger)):
            df[kolom.name] = s.astype("Int64")
        elif isinstance(tipe, Float):
            df[kolom.name] = s.astype(float)
    # Semua nilai kosong (NaN/NaT/<NA>) menjadi NULL
    df = df.astype(object).where(df.notna(), None)
    return df.to_dict("records")


def _reset_sequence(engine: Engine, nama: str) -> None:
    """Di PostgreSQL, id dimasukkan manual dari CSV sehingga sequence harus disusulkan,
    kalau tidak INSERT berikutnya bentrok dengan id yang sudah ada."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as c:
        c.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{nama}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {nama}), 1), "
            f"(SELECT COUNT(*) FROM {nama}) > 0)"
        ))


def _kosongkan(engine: Engine) -> None:
    """Hapus isi semua tabel, struktur dipertahankan, id kembali ke 1."""
    with engine.begin() as c:
        if engine.dialect.name == "postgresql":
            daftar = ", ".join(URUTAN_TABEL)
            c.execute(text(f"TRUNCATE TABLE {daftar} RESTART IDENTITY CASCADE"))
        else:
            for nama in reversed(URUTAN_TABEL):  # anak dulu, baru induk
                c.execute(text(f"DELETE FROM {nama}"))


def _konfirmasi(engine: Engine, yes: bool) -> None:
    if yes or engine.dialect.name == "sqlite":
        return
    tujuan = engine.url.render_as_string(hide_password=True)
    if input(f"Ini akan MENGHAPUS data di {tujuan}\nKetik 'ya' untuk lanjut: ").strip().lower() != "ya":
        sys.exit("Dibatalkan.")


def muat(folder: Path, engine: Engine, reset: bool, kosongkan: bool = False, yes: bool = False) -> None:
    if reset:
        _konfirmasi(engine, yes)
        print("Menghapus semua tabel lama ...")
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    print(f"Tabel siap ({len(Base.metadata.tables)} tabel) di {engine.url.render_as_string(hide_password=True)}")

    with engine.connect() as c:
        terisi = [n for n in URUTAN_TABEL if c.execute(text(f"SELECT 1 FROM {n} LIMIT 1")).first()]
    if terisi and kosongkan:
        _konfirmasi(engine, yes)
        print("Mengosongkan isi tabel (struktur tetap) ...")
        _kosongkan(engine)
    elif terisi:
        sys.exit(f"Tabel sudah berisi data: {', '.join(terisi)}.\n"
                 "Pakai --kosongkan (hapus isi, struktur tetap) atau --reset (bangun ulang tabel).")

    for nama in URUTAN_TABEL:
        berkas = folder / f"{nama}.csv"
        tabel = Base.metadata.tables[nama]
        if not berkas.exists():
            print(f"  {nama:<22} (tidak ada CSV, dibiarkan kosong)")
            continue
        df = pd.read_csv(berkas)
        if nama == "users":
            df["password_hash"] = _hash_demo()  # CSV hanya berisi placeholder
        baris = _siapkan(df, tabel)
        with engine.begin() as c:
            for i in range(0, len(baris), CHUNK):
                c.execute(tabel.insert(), baris[i:i + CHUNK])
        _reset_sequence(engine, nama)
        print(f"  {nama:<22} {len(baris):>8,} baris")
    print("Selesai.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", default="data_dummy", help="folder berisi CSV dari Wulan")
    ap.add_argument("--db-url", default=None, help="timpa alamat database (default: lihat backend/db.py)")
    ap.add_argument("--kosongkan", action="store_true", help="hapus isi semua tabel, struktur dipertahankan")
    ap.add_argument("--reset", action="store_true", help="hapus dan buat ulang semua tabel (untuk perubahan skema)")
    ap.add_argument("--yes", action="store_true", help="lewati pertanyaan konfirmasi (untuk PostgreSQL)")
    a = ap.parse_args()
    folder = Path(a.folder)
    if not folder.is_dir():
        sys.exit(f"Folder tidak ditemukan: {folder}")
    t0 = datetime.now()
    muat(folder, buat_engine(a.db_url), a.reset, a.kosongkan, a.yes)
    print(f"Waktu: {(datetime.now() - t0).total_seconds():.1f} detik")


if __name__ == "__main__":
    main()
