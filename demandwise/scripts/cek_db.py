"""
cek_db.py - cek database yang sedang dipakai aplikasi (HANYA MEMBACA).

Taruh di: demandwise/scripts/cek_db.py
Jalankan dari folder demandwise:
    python -m scripts.cek_db
Alamat database dibaca seperti aplikasi: DEMANDWISE_DB_URL, lalu
.streamlit/secrets.toml, lalu SQLite lokal.
"""
import time
from sqlalchemy import text
from backend.db import buat_engine, ambil_url

TABEL = ["users", "kategori", "pemasok", "produk", "batch_stok",
         "transaksi_penjualan", "detail_penjualan", "mutasi_stok",
         "pesanan_pembelian", "hasil_prediksi", "rekomendasi_tindakan",
         "notifikasi"]


def tampil_alamat(url: str) -> str:
    # sembunyikan user dan password
    if "@" in url:
        return url.split("://")[0] + "://***@" + url.split("@", 1)[1].split("?")[0]
    return url


def main():
    url = ambil_url()
    jenis = "Neon/PostgreSQL" if url.startswith("postgresql") else "SQLite lokal"
    print(f"Database : {jenis}")
    print(f"Alamat   : {tampil_alamat(url)}")
    t0 = time.time()
    try:
        engine = buat_engine()
        with engine.connect() as c:
            c.execute(text("select 1"))
    except Exception as e:
        print("GAGAL terhubung:", str(e).splitlines()[0][:200])
        return
    print(f"Koneksi  : OK ({time.time() - t0:.1f} detik)\n")
    with engine.connect() as c:
        for t in TABEL:
            try:
                n = c.execute(text(f"select count(*) from {t}")).scalar()
                tanda = "  <-- KOSONG" if n == 0 else ""
                print(f"{t:<24}{n:>8} baris{tanda}")
            except Exception:
                c.rollback()
                print(f"{t:<24}  tidak ada tabel")
    print("\nCatatan: hasil_prediksi harus > 0 untuk demo. "
          "Kalau kosong, jalankan jalankan_prediksi(30).")


if __name__ == "__main__":
    main()
