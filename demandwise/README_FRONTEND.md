# Perombakan Tampilan (Frontend) DemandWise

Hanya lapisan tampilan yang diubah. Folder `backend/`, database, `tests/`, dan `scripts/` **tidak diubah**
(seluruh fungsi backend dipanggil dengan nama dan argumen yang sama).

Berkas yang berubah: `app.py`, `components/ui.py`, `assets/style.css`, `.streamlit/config.toml`,
serta aset baru `assets/logo_bulat.png` (logo dipotong bulat).

Tema: cyan `#3DC4F2`, navy `#03426E`, biru royal `#0057C4`, oranye `#E07B0A` (diambil dari logo).
Jalankan seperti biasa: `streamlit run app.py`.

## Buat akun (pendaftaran pengguna)
Halaman login punya dua pilihan: **Masuk** dan **Buat akun**. Formulir daftar mengisi nama usaha, email, username, dan password.
Email disimpan (huruf kecil, unik) di kolom `users.email`; password disimpan sebagai hash bcrypt. Login bisa memakai username atau email.
- Fungsi baru: `daftar_akun(nama_usaha, email, username, password, konfirmasi)` di `backend/auth.py` (diekspor lewat `backend/api.py`).
- Kolom `email` ditambahkan otomatis ke database lama (SQLite maupun Neon) saat daftar/login pertama, lewat `pastikan_kolom_email()` di `backend/db.py`. Tidak perlu reset database.
- Tes: `tests/test_daftar_akun.py`.
