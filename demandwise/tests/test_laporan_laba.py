import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.laba import KOMPONEN, get_laporan_laba, get_laporan_laba_di
from backend.models import (Base, BatchStok, BiayaOperasional, DetailPenjualan, Produk,
                            TransaksiPenjualan, Writeoff)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(Produk(id=1, kode="P1", nama="Beras", harga_beli_terakhir=99999))
        sesi.add(BatchStok(id=1, produk_id=1, tgl_masuk=date(2026, 10, 1),
                           tgl_kedaluwarsa=date(2027, 1, 1), jumlah_awal=100, jumlah_sisa=100,
                           hpp_satuan=8000))
        # 1 Nov: jual 10 @ 10.000 (HPP 8.000) + 5 @ 10.500 (HPP 8.200, batch lain) 
        sesi.add(TransaksiPenjualan(id=1, tanggal=date(2026, 11, 1), total=152500))
        sesi.add_all([
            DetailPenjualan(transaksi_id=1, produk_id=1, batch_id=1, qty=10,
                            harga_satuan=10000, hpp_satuan=8000),
            DetailPenjualan(transaksi_id=1, produk_id=1, batch_id=1, qty=5,
                            harga_satuan=10500, hpp_satuan=8200)])
        # 15 Nov: jual 4 @ 10.000 (HPP 8.000)
        sesi.add(TransaksiPenjualan(id=2, tanggal=date(2026, 11, 15), total=40000))
        sesi.add(DetailPenjualan(transaksi_id=2, produk_id=1, batch_id=1, qty=4,
                                 harga_satuan=10000, hpp_satuan=8000))
        # di luar periode uji utama
        sesi.add(TransaksiPenjualan(id=3, tanggal=date(2026, 12, 1), total=100000))
        sesi.add(DetailPenjualan(transaksi_id=3, produk_id=1, batch_id=1, qty=10,
                                 harga_satuan=10000, hpp_satuan=8000))
        sesi.add_all([BiayaOperasional(tanggal=date(2026, 11, 5), kategori_biaya="Listrik", jumlah=20000),
                      BiayaOperasional(tanggal=date(2026, 11, 30), kategori_biaya="Gaji", jumlah=10000),
                      BiayaOperasional(tanggal=date(2026, 12, 2), kategori_biaya="Sewa", jumlah=77777)])
        sesi.add_all([Writeoff(tanggal=date(2026, 11, 10), batch_id=1, produk_id=1, qty=3,
                               hpp_satuan=8000, total_rugi=24000),
                      Writeoff(tanggal=date(2026, 12, 5), batch_id=1, produk_id=1, qty=1,
                               hpp_satuan=8000, total_rugi=8000)])
        sesi.commit()
        yield sesi


def _angka(df):
    return dict(zip(df["komponen"], df["jumlah"]))


def test_format_dan_urutan_baris_tetap(s):
    df = get_laporan_laba_di(s, date(2026, 11, 1), date(2026, 11, 30))
    assert list(df.columns) == ["komponen", "jumlah"]
    assert list(df["komponen"]) == KOMPONEN


def test_angka_cocok_hitungan_manual(s):
    a = _angka(get_laporan_laba_di(s, date(2026, 11, 1), date(2026, 11, 30)))
    # penjualan = 100.000 + 52.500 + 40.000 = 192.500
    # HPP       = 80.000 + 41.000 + 32.000 = 153.000 (dari batch, bukan harga_beli_terakhir)
    assert a["Penjualan"] == 192500
    assert a["HPP"] == 153000
    assert a["Laba Kotor"] == 39500
    assert a["Biaya Operasional"] == 30000
    assert a["Kerugian Kedaluwarsa (Write-off)"] == 24000
    assert a["Laba Bersih"] == 39500 - 30000 - 24000   # = -14.500 (rugi)


def test_batas_tanggal_ikut_dihitung(s):
    a = _angka(get_laporan_laba_di(s, date(2026, 11, 15), date(2026, 11, 15)))
    assert a["Penjualan"] == 40000
    a = _angka(get_laporan_laba_di(s, date(2026, 11, 30), date(2026, 11, 30)))
    assert a["Biaya Operasional"] == 10000


def test_periode_tanpa_data_semua_nol(s):
    a = _angka(get_laporan_laba_di(s, date(2025, 1, 1), date(2025, 1, 31)))
    assert set(a.values()) == {0}


def test_input_salah_dikembalikan_dataframe_kosong():
    for awal, akhir in [("2026-11-01", date(2026, 11, 30)), (date(2026, 11, 30), date(2026, 11, 1))]:
        df = get_laporan_laba(awal, akhir)
        assert df.empty and list(df.columns) == ["komponen", "jumlah"]
