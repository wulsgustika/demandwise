from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import (Base, DetailPenjualan, Pemasok, Produk,
                            TransaksiPenjualan)
from backend.pembelian import get_prediksi_sementara

HARI = date(2026, 11, 17)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(Pemasok(id=1, nama="Pemasok A", lead_time_hari=3))
        sesi.add_all([
            Produk(id=1, kode="P1", nama="Beras", pemasok_id=1, lead_time_hari=5),
            Produk(id=2, kode="P2", nama="Susu", pemasok_id=1),               # lead time dari pemasok
            Produk(id=3, kode="P3", nama="Roti", pemasok_id=1, aktif=False),  # tidak aktif
        ])
        sesi.commit()
        yield sesi


def _jual(s, tanggal, produk_id, qty):
    t = TransaksiPenjualan(tanggal=tanggal, total=0)
    s.add(t)
    s.flush()
    s.add(DetailPenjualan(transaksi_id=t.id, produk_id=produk_id, batch_id=1,
                          qty=qty, harga_satuan=1000, hpp_satuan=800))


def test_rata_rata_30_hari_dan_lead_time_produk(s):
    _jual(s, HARI - timedelta(days=5), 1, 40)
    _jual(s, HARI - timedelta(days=20), 1, 20)   # total 60 dalam 30 hari -> 2 per hari
    s.commit()
    r = get_prediksi_sementara(s, HARI)[1]
    assert r["lead_time_hari"] == 5
    assert r["prediksi_harian"] == pytest.approx(2.0)
    assert r["prediksi_lead_time"] == pytest.approx(10.0)
    assert r["safety_stock"] == pytest.approx(2.0)


def test_penjualan_lebih_dari_30_hari_tidak_dihitung(s):
    _jual(s, HARI - timedelta(days=40), 1, 100)
    s.commit()
    assert get_prediksi_sementara(s, HARI)[1]["prediksi_harian"] == 0


def test_lead_time_ikut_pemasok_kalau_produk_kosong(s):
    assert get_prediksi_sementara(s, HARI)[2]["lead_time_hari"] == 3


def test_produk_tidak_aktif_tidak_muncul(s):
    assert 3 not in get_prediksi_sementara(s, HARI)
