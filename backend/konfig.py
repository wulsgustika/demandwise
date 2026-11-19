"""
backend/konfig.py - semua konstanta DemandWise (KONTRAK.md bagian 4).

CATATAN INTEGRASI: kalau Naila sudah punya backend/konfig.py, GABUNGKAN saja
(salin blok "KONSTANTA WULAN" di bawah ke file milik Naila). Modul analitik
membaca tiap konstanta lewat getattr dengan nilai bawaan, jadi tidak error
kalau ada yang belum ada.
"""

# ---------------------------------------------------------------------------
# Konstanta bersama (KONTRAK bagian 4)
# ---------------------------------------------------------------------------
LEVEL_WASPADA_HARI = 30          # H-30  (final)
LEVEL_SIAGA_HARI = 14            # H-14  (final)
LEVEL_KRITIS_HARI = 7            # H-7   (final)
AMBANG_INDEKS_MUSIM_LARIS = 1.2  # > 1,2 pada H-30 (final)
MARGIN_MINIMUM_PERSEN = 15       # usulan, putusan Naila

# ---------------------------------------------------------------------------
# KONSTANTA WULAN (ML dan analitik)
# ---------------------------------------------------------------------------
# Tanggal acuan "hari ini":
#   "data"   = sehari setelah transaksi penjualan terakhir di database
#              (cocok untuk data dummy: hari ini = 9 Nov 2026)
#   "sistem" = tanggal komputer/server (PAKAI INI untuk produksi)
# Bisa ditimpa lewat env DEMANDWISE_MODE_TANGGAL.
#   PENTING untuk demo Jumat 20 Nov: skenario batch H-3/H-6/H-12/H-13/H-24/H-29 dibuat relatif terhadap
#   9 Nov 2026. Pakai "data" sampai presentasi selesai. Mode "sistem" hanya setelah data diganti data nyata.
MODE_TANGGAL = "data"

# Safety stock = Z x simpangan baku demand harian x akar(lead time)
Z_SAFETY_STOCK = 1.65
JENDELA_SIGMA_HARI = 90          # simpangan baku dihitung dari N hari terakhir

# Batas status stok (usulan, putusan Wulan + Dhea)
#   menipis   : stok <= reorder point
#   overstock : stok > reorder point + prediksi demand N hari ke depan
OVERSTOCK_HORIZON_HARI = 30

# Fast / slow dan margin tinggi / rendah (usulan: median antarproduk)
PERIODE_PROFIT_HARI = 90         # jendela analisis profit & kecepatan jual
AMBANG_FAST = "median"           # "median" atau angka (unit per hari)
AMBANG_MARGIN = "median"         # "median" atau angka (persen)

# Model prediksi
HORIZON_MINIMAL_HARI = 30        # prediksi selalu disimpan minimal sekian hari
MA_WINDOW_HARI = 14              # baseline moving average
RF_JUMLAH_POHON = 100
RF_MIN_SAMPEL_DAUN = 3
RF_MIN_HARI_DATA = 120           # kurang dari ini: pakai moving average saja
BACKTEST_JUMLAH_FOLD = 2         # evaluasi: N lipatan waktu terakhir
BACKTEST_HORIZON_HARI = 28       # panjang tiap lipatan
KRITERIA_PILIH_MODEL = "mae"     # "mae" | "rmse" | "mape"
BOBOT_KOREKSI_PEMILIK = 0.5      # bobot sampel koreksi pemilik saat latih ulang
HISTORIS_TAMPIL_HARI = 90        # baris 'historis' pada get_prediksi
N_JOBS = 1                       # proses paralel (naikkan kalau server multi-core)

# Level batch (waspada/siaga/kritis):
#   "waktu"  = hanya dari sisa hari: <=30 waspada, <=14 siaga, <=7 kritis (sesuai KONTRAK bagian 5)
#   "risiko" = sama, tapi baru berlevel kalau jumlah_berisiko >= 1
# Notifikasi & rekomendasi tindakan SELALU hanya untuk batch dengan jumlah_berisiko >= 1.
LEVEL_MODE = "waktu"
RETUR_MIN_SISA_HARI = 3          # retur ke pemasok hanya disarankan kalau sisa hari >= ini

# Rekomendasi tindakan batch berisiko: diskon (persen dari harga jual), minimal HPP
DISKON_PERSEN = {"waspada": 10, "siaga": 20, "kritis": 30}
RETUR_MIN_PROPORSI_RISIKO = 0.5  # kritis + risiko >= 50% stok batch -> sarankan retur

# Lokasi modul milik rekan (dicoba berurutan, lihat backend/analitik/_integrasi.py)
MODUL_ENGINE = ["backend.database", "backend.db", "backend.models"]
MODUL_NOTIFIKASI_NADIA = ["backend.notifikasi", "backend.input_data", "backend.nadia", "backend"]
MODUL_LABA_NAILA = ["backend.laba", "backend.laporan", "backend.harga_laba", "backend.naila", "backend"]

# Kalau True, error di fungsi DataFrame dilempar (untuk debugging). Produksi: False.
RAISE_ERROR = False
