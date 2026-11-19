"""Akses konstanta: baca dari backend.konfig bila ada, kalau tidak pakai nilai bawaan di sini.
(Nilai bawaan = salinan blok KONSTANTA di backend/konfig.py.)"""
import importlib

_BAWAAN = {
    'LEVEL_WASPADA_HARI': 30,
    'LEVEL_SIAGA_HARI': 14,
    'LEVEL_KRITIS_HARI': 7,
    'AMBANG_INDEKS_MUSIM_LARIS': 1.2,
    'MARGIN_MINIMUM_PERSEN': 15,
    'MODE_TANGGAL': 'data',
    'Z_SAFETY_STOCK': 1.65,
    'JENDELA_SIGMA_HARI': 90,
    'OVERSTOCK_HORIZON_HARI': 30,
    'PERIODE_PROFIT_HARI': 90,
    'AMBANG_FAST': 'median',
    'AMBANG_MARGIN': 'median',
    'HORIZON_MINIMAL_HARI': 30,
    'MA_WINDOW_HARI': 14,
    'RF_JUMLAH_POHON': 100,
    'RF_MIN_SAMPEL_DAUN': 3,
    'RF_MIN_HARI_DATA': 120,
    'BACKTEST_JUMLAH_FOLD': 2,
    'BACKTEST_HORIZON_HARI': 28,
    'KRITERIA_PILIH_MODEL': 'mae',
    'BOBOT_KOREKSI_PEMILIK': 0.5,
    'HISTORIS_TAMPIL_HARI': 90,
    'N_JOBS': 1,
    'LEVEL_MODE': 'waktu',
    'RETUR_MIN_SISA_HARI': 3,
    'DISKON_PERSEN': {'waspada': 10, 'siaga': 20, 'kritis': 30},
    'RETUR_MIN_PROPORSI_RISIKO': 0.5,
    'MODUL_ENGINE': ['backend.database', 'backend.db', 'backend.models'],
    'MODUL_NOTIFIKASI_NADIA': ['backend.notifikasi', 'backend.input_data', 'backend.nadia', 'backend'],
    'MODUL_LABA_NAILA': ['backend.laba', 'backend.laporan', 'backend.harga_laba', 'backend.naila', 'backend'],
    'RAISE_ERROR': False,
}

try:
    _modul = importlib.import_module("backend.konfig")
except Exception:  # pragma: no cover
    _modul = None

def ambil(nama):
    """Nilai konstanta `nama` (backend.konfig diutamakan, lalu bawaan)."""
    if _modul is not None and hasattr(_modul, nama):
        return getattr(_modul, nama)
    return _BAWAAN[nama]

def __getattr__(nama):
    if nama in _BAWAAN:
        return ambil(nama)
    raise AttributeError(nama)
