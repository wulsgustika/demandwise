"""
cek_data_demo.py - bukti bahwa data dummy/presentasi TIDAK berubah.

Menghitung jumlah baris + sidik (SHA-256) isi setiap tabel untuk data demo
(baris dengan user_id NULL; kolom user_id sendiri tidak ikut dihitung). Skrip ini
TIDAK menjalankan migrasi dan TIDAK menulis apa pun ke database (hanya SELECT).

Pemakaian (dari folder proyek; alamat database sama seperti aplikasi: DEMANDWISE_DB_URL /
.streamlit/secrets.toml / demandwise.sqlite):

    # 1. SEBELUM aplikasi baru dijalankan pertama kali (sebelum migrasi):
    python -m scripts.cek_data_demo --simpan sidik_sebelum.json
    # 2. jalankan aplikasi / python -m scripts.migrasi_multi_pengguna
    # 3. bandingkan:
    python -m scripts.cek_data_demo --banding sidik_sebelum.json
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.db import buat_engine  # noqa: E402  (buat_engine TIDAK menjalankan migrasi)
from backend.models import URUTAN_TABEL  # noqa: E402

KOLOM_USERS = ["id", "username", "password_hash", "nama_usaha"]


def sidik_tabel(conn, insp, tabel: str) -> dict:
    if not insp.has_table(tabel):
        return {"ada": False}
    kolom = [c["name"] for c in insp.get_columns(tabel)]
    if tabel == "users":
        pilih = [k for k in KOLOM_USERS if k in kolom]
        syarat = "WHERE email IS NULL" if "email" in kolom else ""     # akun demo/dummy
    else:
        pilih = [k for k in kolom if k != "user_id"]
        syarat = "WHERE user_id IS NULL" if "user_id" in kolom else ""  # sebelum migrasi: semua = demo
    urut = "ORDER BY id" if "id" in kolom else ""
    daftar = ", ".join(f'"{k}"' for k in pilih)
    h, n = hashlib.sha256(), 0
    for baris in conn.execute(text(f'SELECT {daftar} FROM "{tabel}" {syarat} {urut}')):
        h.update(repr(tuple(baris)).encode())
        n += 1
    return {"ada": True, "baris": n, "sidik": h.hexdigest()}


def sidik_semua(url=None) -> dict:
    eng = buat_engine(url)
    insp = inspect(eng)
    with eng.connect() as conn:
        return {t: sidik_tabel(conn, insp, t) for t in URUTAN_TABEL}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db-url", default=None)
    ap.add_argument("--simpan", help="simpan sidik ke file JSON")
    ap.add_argument("--banding", help="bandingkan dengan file JSON hasil --simpan")
    a = ap.parse_args()
    hasil = sidik_semua(a.db_url)
    for t, v in hasil.items():
        print(f"  {t:<22} {v.get('baris', '-'):>8}  {v.get('sidik', 'tidak ada')[:16]}")
    if a.simpan:
        Path(a.simpan).write_text(json.dumps(hasil, indent=2))
        print(f"Sidik disimpan ke {a.simpan}")
    if a.banding:
        lama = json.loads(Path(a.banding).read_text())
        beda = [t for t in lama if lama[t] != hasil.get(t)]
        if beda:
            print("BERBEDA:", ", ".join(beda))
            sys.exit(1)
        print("SAMA PERSIS: data demo tidak berubah.")


if __name__ == "__main__":
    main()
