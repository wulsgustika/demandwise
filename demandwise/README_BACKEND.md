# DemandWise - Backend gabungan (Naila + Nadia + Wulan)

Satu pintu untuk frontend (Dhea): `from backend.api import ...` (42 fungsi KONTRAK bagian 2).

```
backend/
  api.py            semua fungsi kontrak dalam satu import
  models.py db.py   database, 22 tabel (Naila)
  auth.py penjualan.py stok.py pembelian.py harga.py laba.py   (Naila)
  input_data.py notifikasi.py                                   (Nadia)
  analitik/         ML, stok, kedaluwarsa, musim, profit, dashboard (Wulan)
  konfig.py         konstanta bersama (KONTRAK bagian 4)
```

## Yang tersambung
- Pembelian membaca prediksi dan safety stock dari `get_stok_status()` (Wulan); produk `tunda_pesan` tidak dipesan.
- Harga memakai indeks musim dari tabel `indeks_musim` (Wulan).
- Notifikasi Wulan dikirim lewat `backend.notifikasi.kirim_notifikasi`; dashboard memakai `backend.laba.get_laporan_laba`.
- Satu engine: `backend/db.py` (modul analitik memakai engine yang sama).

## Jalankan
```
pip install -r requirements.txt
python -m pytest tests -q                  # semua tes
python scripts/cek_analitik_db.py          # uji prediksi di database (SQLite/Neon), tempel DEMANDWISE_DB_URL
```
Alamat database: env `DEMANDWISE_DB_URL`, atau `.streamlit/secrets.toml` (lihat `.example`), atau SQLite lokal.
`secrets.toml` JANGAN di-commit dan jangan dikirim.

## Catatan
- Demo: `MODE_TANGGAL = "data"` di `konfig.py` (hari ini = 9 Nov 2026) sampai presentasi selesai.
- Modul Naila (`pembelian`, `harga`, `input_data`) memakai tanggal komputer (`date.today()`); modul analitik memakai tanggal acuan data. Samakan sebelum produksi.
