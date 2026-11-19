from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import (Base, BatchStok, DetailPesanan, Pemasok,
                            PesananPembelian, Produk)
from backend.pembelian import get_pesanan_berjalan, get_stok_per_produk

HARI = date(2026, 11, 17)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(Pemasok(id=1, nama="Pemasok A", lead_time_hari=3))
        sesi.add_all([Produk(id=1, kode="P1", nama="Beras", pemasok_id=1),
                      Produk(id=2, kode="P2", nama="Susu", pemasok_id=1),
                      Produk(id=3, kode="P3", nama="Roti", pemasok_id=1)])
        sesi.commit()
        yield sesi


def _batch(produk_id, sisa, status="aktif"):
    return BatchStok(produk_id=produk_id, tgl_masuk=HARI, tgl_kedaluwarsa=HARI,
                     jumlah_awal=50, jumlah_sisa=sisa, hpp_satuan=1000, status=status)


def _pesanan(s, status, produk_id, qty_final):
    p = PesananPembelian(pemasok_id=1, tanggal=HARI, status=status)
    s.add(p)
    s.flush()
    s.add(DetailPesanan(pesanan_id=p.id, produk_id=produk_id, qty_rekomendasi=qty_final,
                        qty_final=qty_final, harga_beli=1000))


def test_stok_hanya_batch_aktif(s):
    s.add_all([_batch(1, 10), _batch(1, 5),
               _batch(1, 0, "habis"), _batch(1, 7, "kedaluwarsa"),
               _batch(2, 8)])
    s.commit()
    assert get_stok_per_produk(s) == {1: 15, 2: 8}


def test_stok_produk_tanpa_batch_tidak_muncul(s):
    s.add(_batch(1, 10))
    s.commit()
    assert get_stok_per_produk(s).get(3, 0) == 0


def test_pesanan_berjalan_hanya_dipesan_dan_dikirim(s):
    _pesanan(s, "dipesan", 1, 20)
    _pesanan(s, "dikirim", 1, 10)
    _pesanan(s, "draf", 1, 99)
    _pesanan(s, "diterima", 1, 50)
    _pesanan(s, "dibatalkan", 1, 5)
    _pesanan(s, "dipesan", 2, 7)
    s.commit()
    assert get_pesanan_berjalan(s) == {1: 30, 2: 7}


def test_kosong(s):
    assert get_stok_per_produk(s) == {}
    assert get_pesanan_berjalan(s) == {}
