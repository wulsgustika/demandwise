from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.models import (Base, DetailPenjualan, DetailPesanan, Pemasok,
                            PesananPembelian, Produk, TransaksiPenjualan)
from backend.pembelian import buat_draf_dari_rekomendasi

HARI = date(2026, 11, 17)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add_all([Pemasok(id=1, nama="Pemasok A", lead_time_hari=3),
                      Pemasok(id=2, nama="Pemasok B", lead_time_hari=3)])
        sesi.add_all([
            Produk(id=1, kode="P1", nama="Beras", pemasok_id=1, harga_beli_terakhir=9000),
            Produk(id=2, kode="P2", nama="Gula", pemasok_id=1, harga_beli_terakhir=12000),
            Produk(id=3, kode="P3", nama="Susu", pemasok_id=2, harga_beli_terakhir=15000),
            Produk(id=4, kode="P4", nama="Teh", pemasok_id=2, tunda_pesan=True),
            Produk(id=5, kode="P5", nama="Kopi"),   # tanpa pemasok
            Produk(id=6, kode="P6", nama="Roti", pemasok_id=2),  # tidak laku -> qty 0
        ])
        sesi.commit()
        for pid in (1, 2, 3, 4, 5):
            _jual(sesi, pid, 60)    # 2 per hari -> butuh beli (stok 0)
        sesi.commit()
        yield sesi


def _jual(s, produk_id, qty):
    t = TransaksiPenjualan(tanggal=HARI - timedelta(days=5), total=0)
    s.add(t)
    s.flush()
    s.add(DetailPenjualan(transaksi_id=t.id, produk_id=produk_id, batch_id=1,
                          qty=qty, harga_satuan=1000, hpp_satuan=800))


def test_satu_draf_per_pemasok_dengan_detail(s):
    h = buat_draf_dari_rekomendasi(s, HARI)
    s.commit()
    assert len(h["pesanan_id"]) == 2   # Pemasok A (beras, gula) dan Pemasok B (susu)
    pesanan = s.scalars(select(PesananPembelian)).all()
    assert {p.status for p in pesanan} == {"draf"}
    assert {p.pemasok_id for p in pesanan} == {1, 2}
    detail = s.scalars(select(DetailPesanan)).all()
    assert {d.produk_id for d in detail} == {1, 2, 3}   # teh ditunda, kopi tanpa pemasok, roti qty 0
    d1 = next(d for d in detail if d.produk_id == 1)
    assert d1.qty_final == d1.qty_rekomendasi > 0
    assert d1.harga_beli == 9000


def test_yang_dilewati_dilaporkan(s):
    h = buat_draf_dari_rekomendasi(s, HARI)
    assert h["dilewati"]["ditunda"] == ["Teh"]
    assert h["dilewati"]["tanpa_pemasok"] == ["Kopi"]


def test_dua_kali_tidak_menggandakan(s):
    buat_draf_dari_rekomendasi(s, HARI)
    s.commit()
    h2 = buat_draf_dari_rekomendasi(s, HARI)
    s.commit()
    assert h2["pesanan_id"] == []
    assert sorted(h2["dilewati"]["sudah_ada_draf"]) == ["Pemasok A", "Pemasok B"]
    assert len(s.scalars(select(PesananPembelian)).all()) == 2
