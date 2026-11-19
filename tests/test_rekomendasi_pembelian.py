from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import (Base, BatchStok, DetailPenjualan, Pemasok, Produk,
                            TransaksiPenjualan)
from backend.pembelian import KOLOM_REKOMENDASI, hitung_rekomendasi_pembelian

HARI = date(2026, 11, 17)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(Pemasok(id=1, nama="Pemasok A", lead_time_hari=3))
        sesi.add_all([
            # umur simpan 6, lead time 5 -> sisa umur 1 hari
            Produk(id=1, kode="P1", nama="Beras", pemasok_id=1, lead_time_hari=5, umur_simpan_hari=6),
            # umur simpan 100, lead time 3 (dari pemasok) -> sisa umur 97
            Produk(id=2, kode="P2", nama="Susu", pemasok_id=1, umur_simpan_hari=100, tunda_pesan=True),
            Produk(id=3, kode="P3", nama="Roti", pemasok_id=1, aktif=False),
        ])
        sesi.commit()
        yield sesi


def _jual(s, produk_id, qty, hari_lalu=5):
    t = TransaksiPenjualan(tanggal=HARI - timedelta(days=hari_lalu), total=0)
    s.add(t)
    s.flush()
    s.add(DetailPenjualan(transaksi_id=t.id, produk_id=produk_id, batch_id=1,
                          qty=qty, harga_satuan=1000, hpp_satuan=800))


def test_kolom_dan_urutan_sesuai_kontrak(s):
    df = hitung_rekomendasi_pembelian(s, HARI)
    assert list(df.columns) == KOLOM_REKOMENDASI
    assert list(df["nama_produk"]) == ["Beras", "Susu"]   # produk tidak aktif tidak muncul


def test_satu_produk_dihitung_lengkap(s):
    _jual(s, 1, 60)   # 2 per hari -> prediksi_lead_time 10, safety stock 2
    s.add(BatchStok(produk_id=1, tgl_masuk=HARI, tgl_kedaluwarsa=HARI, jumlah_awal=5,
                    jumlah_sisa=4, hpp_satuan=800, status="aktif"))
    s.commit()
    r = hitung_rekomendasi_pembelian(s, HARI).set_index("produk_id").loc[1]
    assert r["pemasok"] == "Pemasok A"
    assert r["stok_saat_ini"] == 4
    assert r["prediksi_lead_time"] == pytest.approx(10.0)
    assert r["safety_stock"] == pytest.approx(2.0)
    assert r["qty_hitung"] == 8              # 10 + 2 - 4 - 0
    assert r["batas_masa_simpan"] == 2       # 2 per hari x sisa umur 1 hari
    assert r["qty_rekomendasi"] == 2         # dibatasi masa simpan
    assert r["ditunda"] == False


def test_produk_ditunda_ditandai(s):
    df = hitung_rekomendasi_pembelian(s, HARI).set_index("produk_id")
    assert df.loc[2, "ditunda"] == True
    assert df.loc[1, "ditunda"] == False


def test_tanpa_penjualan_rekomendasi_nol(s):
    df = hitung_rekomendasi_pembelian(s, HARI)
    assert (df["qty_rekomendasi"] == 0).all()
