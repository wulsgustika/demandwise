"""
Isi tabel hasil ML pada SQLite dummy (hasil_prediksi, indeks_musim, evaluasi_model,
rekomendasi_tindakan, notifikasi, event_musiman), supaya dashboard langsung punya data.

    python scripts/siapkan_db_demo.py                      # pakai data_dummy/demandwise_dummy.sqlite
    python scripts/siapkan_db_demo.py path/ke/lain.sqlite
    python scripts/siapkan_db_demo.py --reset              # kosongkan dulu tabel hasil ML, lalu isi ulang
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine  # noqa: E402

from backend.analitik import _db, jalankan_prediksi  # noqa: E402

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else _db.PATH_SQLITE_DUMMY
    _db.set_engine(create_engine(f"sqlite:///{path}"))
    if "--reset" in sys.argv:
        _db.get_engine()  # pastikan tabel ML ada
        for t in ("hasil_prediksi", "indeks_musim", "evaluasi_model", "rekomendasi_tindakan", "notifikasi",
                  "koreksi_prediksi"):
            _db.jalankan(f"DELETE FROM {t}")
        _db.jalankan("UPDATE produk SET tunda_pesan = :v", {"v": False})
    r = jalankan_prediksi(30, progress=lambda i, n, nm: print(f"\r{i}/{n} {nm:<35}", end="", flush=True))
    print()
    print(r["pesan"])
    print(r["data"])
