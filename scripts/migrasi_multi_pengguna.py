"""
migrasi_multi_pengguna.py - jalankan migrasi multi-pengguna secara manual dan tampilkan laporannya.

Aplikasi juga menjalankannya otomatis saat pertama kali terhubung ke database, jadi skrip
ini opsional (berguna untuk melihat apa yang dikerjakan di Neon sebelum presentasi).
Migrasi hanya MENAMBAH kolom/indeks; tidak ada TRUNCATE/DELETE/DROP data. Lihat backend/migrasi.py.

    python -m scripts.migrasi_multi_pengguna
    python -m scripts.migrasi_multi_pengguna --db-url "postgresql://..."
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.db import buat_engine  # noqa: E402
from backend.migrasi import pastikan_skema_multi_pengguna  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db-url", default=None)
    a = ap.parse_args()
    eng = buat_engine(a.db_url)
    print("Database:", eng.url.render_as_string(hide_password=True))
    laporan = pastikan_skema_multi_pengguna(eng, paksa=True)
    if not laporan["langkah"]:
        print("Skema sudah siap, tidak ada yang perlu diubah.")
    for l in laporan["langkah"]:
        print(" -", l)


if __name__ == "__main__":
    main()
