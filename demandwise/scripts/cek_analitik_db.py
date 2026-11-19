"""
Uji backend Wulan di PostgreSQL (Neon/Supabase): jalankan prediksi lalu cek semua fungsi kontrak.

    python scripts/cek_analitik_db.py                  # URL ditanya lewat prompt (password tidak tersimpan di file)
    python scripts/cek_analitik_db.py "postgresql://user:pass@host/db?sslmode=require"
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

url = sys.argv[1] if len(sys.argv) > 1 else (os.environ.get("DEMANDWISE_DB_URL")
                                              or input("Tempel DEMANDWISE_DB_URL (postgresql://...): ").strip())
os.environ["DEMANDWISE_DB_URL"] = url      # engine Naila (backend/db.py) dipakai juga oleh modul analitik

from backend.analitik import (_db, evaluasi_dan_retrain, get_event_musiman, get_evaluasi_model,  # noqa: E402
                              get_indeks_musim, get_prediksi, get_profit_produk, get_rekomendasi_tindakan,
                              get_ringkasan_dashboard, get_risiko_kedaluwarsa, get_stok_status, get_tren_produk,
                              jalankan_prediksi, setujui_tindakan)

hasil = []


def cek(nama, fn, syarat):
    try:
        v = fn()
        ok = bool(syarat(v))
        info = v if isinstance(v, (int, str)) else (len(v) if hasattr(v, "__len__") else v)
    except Exception as e:  # noqa
        ok, info = False, f"ERROR: {e}"
    hasil.append(ok)
    print(f"[{'OK ' if ok else 'GAGAL'}] {nama}: {info}")


print("Database:", _db.get_engine().dialect.name)
t0 = time.time()
r = jalankan_prediksi(30, progress=lambda i, n, nm: print(f"\r  prediksi {i}/{n}", end="", flush=True))
print()
hasil.append(r["ok"])
print(f"[{'OK ' if r['ok'] else 'GAGAL'}] jalankan_prediksi: {r['pesan']} ({time.time() - t0:.0f} detik)")
if not r["ok"]:
    sys.exit("Berhenti: jalankan_prediksi gagal. Kalau pesannya 'Belum ada data penjualan', "
             "isi dulu tabel dengan scripts/muat_ke_postgres.py atau data Naila.")

cek("get_prediksi(1)", lambda: get_prediksi(1), lambda d: len(d) > 30)
cek("get_stok_status", get_stok_status, lambda d: len(d) > 0 and set(d["status"]) <= {"menipis", "aman", "overstock"})
cek("get_risiko_kedaluwarsa", get_risiko_kedaluwarsa, lambda d: len(d) > 0)
cek("get_indeks_musim", get_indeks_musim, lambda d: len(d) > 0)
cek("get_event_musiman", get_event_musiman, lambda d: len(d) > 0)
cek("get_profit_produk", get_profit_produk, lambda d: len(d) > 0)
cek("get_tren_produk", get_tren_produk, lambda d: len(d) > 0)
cek("get_evaluasi_model", get_evaluasi_model, lambda d: len(d) > 0)
cek("get_rekomendasi_tindakan", get_rekomendasi_tindakan, lambda d: True)
cek("get_ringkasan_dashboard", get_ringkasan_dashboard, lambda d: "penjualan_30_hari" in d and "total_produk_aktif" in d)
cek("notifikasi tersimpan", lambda: int(_db.baca("SELECT COUNT(*) AS n FROM notifikasi")["n"].iloc[0]), lambda n: n > 0)

rek = get_rekomendasi_tindakan()
menunggu = rek[rek["status"] == "menunggu"] if len(rek) else rek
if len(menunggu):
    rid = int(menunggu["id"].iloc[0])
    cek("setujui_tindakan (tulis tunda_pesan)", lambda: setujui_tindakan(rid)["ok"], lambda x: x is True)

print("\nHASIL:", "SEMUA LULUS" if all(hasil) else "ADA YANG GAGAL (lihat baris GAGAL di atas)")
