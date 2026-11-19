import pytest

from backend.harga import (MARGIN_MINIMUM, harga_untuk_margin, hitung_harga_rekomendasi,
                           hitung_margin_persen)


def test_tanpa_musim_dan_pesaing_pakai_margin_target():
    # HPP 7.500, margin 25% -> 10.000 (pas kelipatan 500)
    h = hitung_harga_rekomendasi(7500)
    assert h["harga"] == 10000
    assert "margin target" in h["alasan"]


def test_dibulatkan_ke_atas_kelipatan_500():
    # 8.000 / 0,75 = 10.666,67 -> 11.000
    assert hitung_harga_rekomendasi(8000)["harga"] == 11000


def test_musim_laris_menaikkan_harga():
    biasa = hitung_harga_rekomendasi(7500)["harga"]
    laris = hitung_harga_rekomendasi(7500, indeks_musim=1.4)
    assert laris["harga"] > biasa
    assert "indeks musim" in laris["alasan"]


def test_musim_sepi_menurunkan_harga_tapi_tidak_di_bawah_margin_minimum():
    h = hitung_harga_rekomendasi(7500, indeks_musim=0.1)
    assert h["harga"] < hitung_harga_rekomendasi(7500)["harga"]
    assert h["harga"] >= harga_untuk_margin(7500, MARGIN_MINIMUM)


def test_pengaruh_musim_dibatasi():
    # indeks ekstrem tidak boleh menaikkan lebih dari +10% dari harga dasar
    dasar = 7500 / 0.75
    h = hitung_harga_rekomendasi(7500, indeks_musim=50)["harga"]
    assert h <= dasar * 1.10 + 500


def test_harga_pesaing_membatasi_harga_atas():
    # HPP 6.000 -> harga dasar 8.000; pesaing rata-rata 7.000 -> batas 7.350
    # (masih di atas lantai margin minimum 7.059), jadi harga ditahan ke ~7.500
    h = hitung_harga_rekomendasi(6000, harga_pesaing_rata2=7000)
    assert h["harga"] == 7500
    assert "pesaing" in h["alasan"]


def test_margin_minimum_menang_atas_pesaing_murah():
    # pesaing jual 8.000, tapi HPP kita 7.500: margin minimum 15% -> >= 8.823
    h = hitung_harga_rekomendasi(7500, harga_pesaing_rata2=8000)
    assert h["harga"] >= harga_untuk_margin(7500, MARGIN_MINIMUM)
    assert hitung_margin_persen(h["harga"], 7500) >= 15
    assert "margin minimum" in h["alasan"]


def test_margin_selalu_minimal_15_persen_untuk_banyak_kombinasi():
    for hpp in (1000, 2750, 7500, 18300, 95000):
        for idx in (None, 0.5, 1.0, 1.5, 3.0):
            for pes in (None, 1, hpp, hpp * 3):
                h = hitung_harga_rekomendasi(hpp, idx, pes)["harga"]
                assert hitung_margin_persen(h, hpp) >= 15, (hpp, idx, pes, h)


def test_hpp_tidak_valid_ditolak():
    for hpp in (0, -100, None):
        with pytest.raises(ValueError):
            hitung_harga_rekomendasi(hpp)


def test_hitung_margin_persen():
    assert hitung_margin_persen(10000, 7500) == 25.0
    assert hitung_margin_persen(0, 7500) == 0.0
