# Data dummy DemandWise (24 bulan)

Dibuat oleh `seed_dummy_demandwise.py` (seed tetap 42, hasil selalu sama).
Periode penjualan: **9 Nov 2024 sampai 8 Nov 2026** (730 hari). "Hari ini" = 9 Nov 2026.

## Isi
16 CSV, nama tabel dan kolom sama persis dengan KONTRAK.md bagian 1, ditambah
`demandwise_dummy.sqlite` (semua tabel yang sama, untuk dipakai lokal).

43 produk, 8 kategori, 7 pemasok. 30.375 transaksi, 165.456 baris detail penjualan.
Tabel milik fungsi ML (`hasil_prediksi`, `indeks_musim`, `evaluasi_model`, `koreksi_prediksi`,
`rekomendasi_tindakan`, `notifikasi`) sengaja kosong: diisi oleh fungsi backend.

## Yang konsisten
- Stok disimulasikan harian: pesan ke pemasok, batch masuk, jual lewat FEFO, kedaluwarsa, write-off.
- `jumlah_sisa` tiap batch = jumlah semua `mutasi_stok` batch itu.
- Penjualan tidak pernah memakai batch yang sudah kedaluwarsa.
- `transaksi_penjualan.total` = jumlah (qty x harga_satuan) detailnya.

## Pola yang sengaja ditanam (untuk model dan demo)
- Tren naik 8-14% per tahun, pola hari (Sabtu tertinggi), efek gajian (tgl 25-3).
- Musim: Ramadan, Lebaran (naik bertahap, turun sesudahnya), Natal (mulai 10 Des),
  Tahun Ajaran Baru (Juli), kemarau (Jun-Sep, minuman).
  Contoh: Kue Nastar naik sekitar 9x, Kurma 6x, Biskuit Kaleng 5x, Buku Tulis 3x.
- Produk cepat (Mi Instan, Air Mineral) sampai lambat (Kurma, Nastar, Biskuit Kaleng).
- Produk masa simpan pendek (Roti 5-7 hari, Telur dan Yogurt 21 hari, Nastar 60 hari)
  menghasilkan write-off alami: 134 kejadian, Rp 15,2 juta.
- Toko tutup 4 hari (Idul Fitri): hari tanpa transaksi, cocok untuk latihan missing value.
- Lonjakan permintaan acak sekitar 0,3% hari (outlier).
- Harga beli dan jual naik 4 kali (Apr 2025, Okt 2025, Apr 2026, Sep 2026).
- Stockout jarang (sekitar 0,4% hari-buka produk cepat).

## Skenario demo (kondisi per 9 Nov 2026)
- 59 batch aktif. Banyak produk yang stoknya tinggal 0-4 hari, jadi `stok_menipis` akan muncul.
- 6 batch sengaja dibuat mendekati kedaluwarsa:
  kritis (H-3, H-6): Tisu Gulung, Kaldu Bubuk; siaga (H-12, H-13): Teh Celup, Beras Premium;
  waspada (H-24, H-29): Kurma, Sabun Cuci Piring.
- Natal 2026 dimulai 10 Des = tepat H-30 dari 10 Nov, jadi `musim_mendekat` bisa dicoba besok.
- 8 pesanan berstatus `dikirim` dan 6 `dipesan` (pesanan berjalan untuk rumus beli Naila).

## Asumsi yang perlu disetujui Naila dan Nadia
1. `mutasi_stok.qty` **bertanda**: masuk dan opname-lebih positif; penjualan, retur (ke pemasok),
   rusak, write-off, dan opname-kurang negatif. Retur dianggap retur ke pemasok.
2. Penjualan di `mutasi_stok` dicatat **agregat per hari per produk per batch** (bukan per transaksi).
3. `users`: username `pemilik`, password `demo123` (hash bcrypt jika library tersedia).
4. Tanggal Ramadan dan Lebaran adalah perkiraan, bukan kalender resmi.
5. `produk.lead_time_hari` sama dengan lead time pemasoknya.
6. Semua `tgl_masuk` stok awal = 8 Nov 2024 (satu hari sebelum penjualan dimulai).
