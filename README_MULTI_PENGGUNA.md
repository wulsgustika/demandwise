# DemandWise - Akun Pengguna & Pemisahan Data (multi-pengguna)

Dua mode berjalan berdampingan di database yang sama (Neon PostgreSQL atau SQLite lokal):

| Mode | Akun | Data yang dilihat & ditulis |
|---|---|---|
| **Demo / presentasi** | akun lama tanpa email, mis. `pemilik` / `demo123` (`users.akun_demo = TRUE`) | data dummy: semua baris dengan `user_id IS NULL` |
| **Pengguna aktual** | akun dari menu **Buat akun** (`users.akun_demo = FALSE`) | hanya baris dengan `user_id = id akunnya`; akun baru mulai **kosong** |

## Cara kerjanya
- **Skema**: 21 tabel data mendapat kolom `user_id` (NULL, FK ke `users.id`, berindeks). `users` mendapat kolom `akun_demo`.
  `produk.kode` dan `kategori.nama` sekarang unik **per pemilik data** (akun A & B boleh sama-sama punya kode `PRD-001`).
- **Migrasi aman** (`backend/migrasi.py`) berjalan otomatis saat aplikasi pertama terhubung ke database. Hanya menambah
  kolom/indeks. Tidak ada TRUNCATE/DELETE/DROP data. Baris dummy lama tidak diubah (user_id-nya tetap NULL).
  Di SQLite, file database dicadangkan dulu (`*.cadangan-*.sqlite`).
- **Siapa yang login** disimpan di `st.session_state` saat login (`backend/konteks.py`).
- **Penyaringan otomatis** (`backend/db.py`): setiap query ORM dibatasi ke `user_id` akun yang login, dan baris baru otomatis
  diberi `user_id` akun itu. Query SQL modul analitik memakai `_db.saring()` / `_db.kondisi()` dengan aturan yang sama.
  Mengakses data milik akun lain lewat id ditolak ("tidak ditemukan").
- **Tanpa data dummy otomatis**: akun baru tidak dibuatkan produk, event, prediksi, dll. Data tersimpan hanya saat pengguna
  mengisinya. Kategori/pemasok baru boleh diketik langsung di form Tambah produk.
- Tanggal acuan analitik: mode demo tetap memakai tanggal data dummy (9 Nov 2026), akun pengguna memakai tanggal hari ini.

## Menjalankan di Neon
```
# (opsional, disarankan) catat sidik data demo SEBELUM aplikasi baru dijalankan:
python -m scripts.cek_data_demo --simpan sidik_sebelum.json
# migrasi (otomatis juga saat `streamlit run app.py`); aman diulang:
python -m scripts.migrasi_multi_pengguna
# buktikan data demo sama persis:
python -m scripts.cek_data_demo --banding sidik_sebelum.json
```
Alamat database dibaca seperti biasa (`DEMANDWISE_DB_URL` atau `.streamlit/secrets.toml`).

**Jangan** menjalankan `scripts.muat_ke_postgres --kosongkan/--reset` atau `scripts/siapkan_db_demo.py --reset`:
opsi lama itu memang menghapus isi tabel (termasuk akun & data pengguna).

## Tes
```
python -m pytest tests -q                         # semua tes (termasuk tests/test_multi_pengguna.py)
# opsional, pada database UJI (mis. branch Neon), bukan database utama:
DW_UJI_DB_URL="postgresql://..." python -m pytest tests/test_multi_pengguna.py -q
```
## Fitur akun (menu **Profil & Akun** dan halaman login)
| Fitur | Tabel baru | Keterangan |
|---|---|---|
| Profil usaha | `profil_usaha` | Nama usaha, pemilik, telepon, jenis usaha, alamat, kota, logo. Diisi bertahap; baris dibuat hanya saat disimpan. |
| Ganti password | (tabel `users`) | Wajib password lama; login di perangkat lain otomatis keluar. |
| Lupa password | `token_reset_password` | Kode 6 angka lewat email, berlaku 15 menit, sekali pakai, maks 5x salah, maks 3 permintaan/15 menit. Disimpan sebagai hash. |
| Sesi bertahan | `sesi_login` | "Ingat saya" 7 hari lewat cookie `dw_sesi`; token disimpan sebagai hash; tombol Keluar mencabut sesi. |

- Akun demo (`pemilik`) dikunci: profil dan password tidak bisa diubah, supaya login presentasi tetap `demo123`.
- Email: isi bagian `[email]` di `.streamlit/secrets.toml` (lihat `.streamlit/secrets.toml.example`). Tanpa itu,
  kode reset tampil di **terminal** tempat `streamlit run app.py` berjalan (cukup untuk demo).
- Sesi bertahan butuh `streamlit>=1.42` (sudah di requirements.txt). Versi lama tetap jalan, hanya login hilang saat refresh.
- Tes: `tests/test_akun.py`.

ERD terbaru: `docs/erd.mermaid` dan `docs/erd_multi_pengguna.png`.
