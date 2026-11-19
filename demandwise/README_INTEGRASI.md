# DemandWise - Project Terintegrasi

Project ini menggabungkan **tampilan frontend DemandWise** dengan **backend final dan database**.

## Yang dipakai
- `app.py`: antarmuka utama yang sudah diarahkan ke fungsi backend final.
- `backend/`: backend final (API, autentikasi, database, stok, pembelian, harga, laba, dan analitik).
- `demandwise.sqlite`: database SQLite bawaan project.
- `assets/` dan `components/`: aset visual dan komponen tampilan frontend.
- `pages_asli/`: salinan seluruh halaman frontend lama, disimpan agar desain dan kode halaman sebelumnya tidak hilang. Halaman-halaman ini belum menjadi halaman aktif karena masih memanggil modul backend lama.
- `tests/`: pengujian backend yang disertakan pada ZIP backend.

## Menjalankan di Windows / VS Code
1. Ekstrak ZIP ini.
2. Buka folder `demandwise` di VS Code (folder yang berisi `app.py` dan `requirements.txt`).
3. Buka Terminal > New Terminal.
4. Buat virtual environment:
   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   Jika PowerShell menolak aktivasi, jalankan `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, lalu aktifkan lagi.
5. Pasang library:
   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
6. Jalankan aplikasi:
   ```powershell
   streamlit run app.py
   ```
7. Browser akan membuka alamat lokal Streamlit, biasanya `http://localhost:8501`.

Alternatif: klik dua kali `JALANKAN_DEMANDWISE.bat` setelah langkah instalasi library selesai.

## Login
Gunakan akun yang sudah terdaftar di database. Dokumentasi database menyebut akun demo:
- Username: `pemilik`
- Password: `demo123`

Jika login gagal, jangan membuat akun baru secara manual. Periksa apakah `demandwise.sqlite` berada satu folder dengan `app.py` dan pastikan tidak ada `DEMANDWISE_DB_URL` yang mengarahkan aplikasi ke database lain.

## Memakai database PostgreSQL / Neon
Secara default aplikasi memakai `demandwise.sqlite`. Jika ingin memakai database lain, atur variabel lingkungan `DEMANDWISE_DB_URL` atau isi `.streamlit/secrets.toml` mengikuti contoh pada `backend/db.py`. Jangan membagikan file `secrets.toml` karena dapat berisi kredensial.

## Batas integrasi saat ini
Antarmuka utama sudah memakai fungsi backend final untuk login, produk, stok/batch, penjualan, pembelian, harga, laporan laba, analitik, risiko kedaluwarsa, event musiman, dan notifikasi. Beberapa halaman lama seperti tugas gudang/verifikasi laporan multi-role belum diaktifkan karena model backend final tidak menyediakan role dan tabel khusus untuk alur tersebut. Kode halaman lamanya tetap disimpan di `pages_asli/` sebagai referensi, bukan diklaim sudah terhubung.

## Catatan pengujian
Sumber backend dan aplikasi sudah diperiksa kompilasi sintaks Python (`compileall`). Pengujian runtime penuh belum dapat dilakukan di lingkungan pembuatan ZIP karena paket `streamlit` dan `bcrypt` tidak tersedia dan instalasi paket memerlukan koneksi internet. Jalankan instalasi dependensi dan tes di komputer lokal sebelum presentasi:
```powershell
python -m pytest tests -q
```

## Pembaruan frontend v3 (backend tidak diubah)
Folder `backend/`, `tests/`, dan file database identik dengan versi sebelumnya. Perubahan hanya di `app.py`, `components/`, dan `requirements.txt`.
- **Pembelian > Proses Pesanan**: tinjau rincian, revisi Qty final (`revisi_pesanan`), setujui, catat jadwal kirim (`simpan_jadwal_kirim`), terima barang. Aksi menyesuaikan status pesanan.
- **Koreksi Prediksi** (menu baru): grafik model vs koreksi, form koreksi (`simpan_koreksi`), daftar koreksi aktif, tombol retrain.
- **Event Musiman > Indeks Musim**: heatmap produk x bulan dengan event terkait.
- **Prediksi & Analitik > Evaluasi Model**: riwayat retrain per versi (MAPE, MAE, RMSE), produk dengan galat terbesar.
- **Risiko Kedaluwarsa**: tab Tugas Tindak Lanjut (dari rekomendasi yang disetujui), opsi Tetapkan tindakan lain (`tolak_tindakan` dengan teks), dan perbaikan hitungan Rekomendasi Menunggu.
- **Notifikasi**: filter kategori, pencarian, tombol Buka halaman terkait.
- **Ekspor** CSV, Excel, PDF di tabel utama (butuh `openpyxl` dan `reportlab`: `pip install -r requirements.txt`).
- **Validasi form** di sisi layar untuk login, produk, barang masuk, rusak/retur, biaya, event, harga manual, dan koreksi.

Belum dibuat karena backend tidak punya role: sidebar per role, verifikasi laporan laba oleh Manajer, review Manajer sebelum persetujuan Pemilik, notifikasi per role.
