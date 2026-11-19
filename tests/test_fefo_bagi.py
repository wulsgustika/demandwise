"""Tes langkah 2: pembagian qty ke batch. Murni hitungan, tanpa database."""
from types import SimpleNamespace as B

from backend.penjualan import bagi_ke_batch


def _hasil(alokasi):
    return [(b.nama, n) for b, n in alokasi]


def test_cukup_dari_satu_batch():
    a, b = B(nama="A", jumlah_sisa=6), B(nama="B", jumlah_sisa=20)
    alokasi, kurang = bagi_ke_batch([a, b], 5)
    assert _hasil(alokasi) == [("A", 5)] and kurang == 0


def test_terpecah_ke_dua_batch():
    # contoh di penjelasan: jual 10, A sisa 6, B sisa 20 -> 6 dari A, 4 dari B
    a, b, c = B(nama="A", jumlah_sisa=6), B(nama="B", jumlah_sisa=20), B(nama="C", jumlah_sisa=50)
    alokasi, kurang = bagi_ke_batch([a, b, c], 10)
    assert _hasil(alokasi) == [("A", 6), ("B", 4)] and kurang == 0


def test_pas_menghabiskan_batch():
    a, b = B(nama="A", jumlah_sisa=6), B(nama="B", jumlah_sisa=20)
    alokasi, kurang = bagi_ke_batch([a, b], 6)
    assert _hasil(alokasi) == [("A", 6)] and kurang == 0   # B tidak tersentuh


def test_stok_kurang():
    a, b = B(nama="A", jumlah_sisa=6), B(nama="B", jumlah_sisa=4)
    alokasi, kurang = bagi_ke_batch([a, b], 15)
    assert _hasil(alokasi) == [("A", 6), ("B", 4)] and kurang == 5


def test_tanpa_batch():
    assert bagi_ke_batch([], 3) == ([], 3)


def test_tidak_mengubah_batch():
    a = B(nama="A", jumlah_sisa=6)
    bagi_ke_batch([a], 4)
    assert a.jumlah_sisa == 6   # langkah ini hanya menghitung
