"""
backend/api.py - SATU PINTU ke semua fungsi KONTRAK.md bagian 2 (untuk Dhea / frontend).

    from backend.api import login, get_produk, simpan_penjualan, get_stok_status, get_laporan_laba, ...

Isinya hanya mengumpulkan fungsi yang sudah ada, tanpa mengubah nama, kolom, atau rumus (KONTRAK aturan 4).
Pemilik tiap fungsi tetap sama dengan kolom "Pemilik" di KONTRAK.
"""
# 2.1 Fondasi dan input (Naila / Nadia)
from .auth import daftar_akun, login
from .akun import (buat_sesi, cabut_sesi, cek_sesi, ganti_password, get_profil, minta_reset_password,
                   reset_password, simpan_profil)
from .input_data import (catat_barang_rusak, catat_retur, catat_writeoff, get_batch, get_notifikasi,
                         get_produk, impor_csv, simpan_biaya, simpan_opname, tambah_produk, tandai_dibaca)
from .notifikasi import kirim_notifikasi
from .penjualan import simpan_penjualan
from .stok import catat_barang_masuk
# 2.2 Pembelian, harga, laba (Naila)
from .harga import get_rekomendasi_harga, setujui_harga, ubah_harga_manual
from .laba import get_laporan_laba
from .pembelian import (buat_draf_pesanan, get_rekomendasi_pembelian, get_teks_pesanan_wa, revisi_pesanan,
                        setujui_pesanan, simpan_jadwal_kirim, terima_pesanan)
# 2.3 ML dan analitik (Wulan)
from .analitik import (evaluasi_dan_retrain, get_event_musiman, get_evaluasi_model, get_indeks_musim,
                       get_prediksi, get_profit_produk, get_rekomendasi_tindakan, get_ringkasan_dashboard,
                       get_risiko_kedaluwarsa, get_stok_status, get_tren_produk, jalankan_prediksi,
                       setujui_tindakan, simpan_event, simpan_koreksi, tolak_tindakan)

__all__ = [
    "login", "daftar_akun", "get_profil", "simpan_profil", "ganti_password", "minta_reset_password",
    "reset_password", "buat_sesi", "cek_sesi", "cabut_sesi", "get_produk", "tambah_produk", "simpan_penjualan", "catat_barang_masuk", "catat_retur",
    "catat_barang_rusak", "get_batch", "simpan_opname", "simpan_biaya", "catat_writeoff", "impor_csv",
    "kirim_notifikasi", "get_notifikasi", "tandai_dibaca",
    "get_rekomendasi_pembelian", "buat_draf_pesanan", "setujui_pesanan", "revisi_pesanan",
    "get_teks_pesanan_wa", "simpan_jadwal_kirim", "terima_pesanan", "get_rekomendasi_harga",
    "setujui_harga", "ubah_harga_manual", "get_laporan_laba",
    "jalankan_prediksi", "get_prediksi", "get_stok_status", "get_risiko_kedaluwarsa",
    "get_rekomendasi_tindakan", "setujui_tindakan", "tolak_tindakan", "get_indeks_musim",
    "get_event_musiman", "simpan_event", "get_profit_produk", "get_tren_produk", "simpan_koreksi",
    "evaluasi_dan_retrain", "get_evaluasi_model", "get_ringkasan_dashboard",
]
