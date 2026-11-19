"""
backend.analitik  -  bagian Wulan (ML dan analitik) dari backend DemandWise.

Semua fungsi di KONTRAK.md bagian 2.3 diekspor dari sini:

    from backend.analitik import get_prediksi, get_stok_status, jalankan_prediksi, ...
"""
from .dashboard import get_ringkasan_dashboard
from .kedaluwarsa import (get_rekomendasi_tindakan, get_risiko_kedaluwarsa, setujui_tindakan,
                          tolak_tindakan)
from .musiman import get_event_musiman, get_indeks_musim, simpan_event
from .prediksi import (evaluasi_dan_retrain, get_evaluasi_model, get_prediksi, jalankan_prediksi,
                       simpan_koreksi)
from .profit import get_profit_produk, get_tren_produk
from .stok import get_stok_status
from ._db import set_engine

__all__ = [
    "jalankan_prediksi", "get_prediksi", "get_stok_status", "get_risiko_kedaluwarsa",
    "get_rekomendasi_tindakan", "setujui_tindakan", "tolak_tindakan", "get_indeks_musim",
    "get_event_musiman", "simpan_event", "get_profit_produk", "get_tren_produk", "simpan_koreksi",
    "evaluasi_dan_retrain", "get_evaluasi_model", "get_ringkasan_dashboard", "set_engine",
]
