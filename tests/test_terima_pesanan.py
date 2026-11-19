import pytest
from datetime import date
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.models import (Base, BatchStok, DetailPesanan, MutasiStok, Pemasok,
                            PesananPembelian, Produk, User)
from backend.pembelian import get_teks_pesanan_wa_di, terima_pesanan_di

HARI = date(2026, 11, 20)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(User(username="pemilik", password_hash="x", nama_usaha="Toko Berkah"))
        sesi.add(Pemasok(id=1, nama="CV Sumber", lead_time_hari=3))
        sesi.add_all([
            Produk(id=1, kode="P1", nama="Beras", satuan="kg", pemasok_id=1,
                   umur_simpan_hari=100, harga_beli_terakhir=8000),
            Produk(id=2, kode="P2", nama="Gula", satuan="kg", pemasok_id=1, umur_simpan_hari=200),
            Produk(id=3, kode="P3", nama="Teh", pemasok_id=1, umur_simpan_hari=50),
            Produk(id=4, kode="P4", nama="Kopi", pemasok_id=1, umur_simpan_hari=None)])
        for pid, status in ((1, "dikirim"), (2, "dipesan"), (3, "dikirim")):
            sesi.add(PesananPembelian(id=pid, pemasok_id=1, tanggal=date(2026, 11, 17), status=status))
        sesi.add_all([
            DetailPesanan(pesanan_id=1, produk_id=1, qty_rekomendasi=50, qty_final=50, harga_beli=9000),
            DetailPesanan(pesanan_id=1, produk_id=2, qty_rekomendasi=30, qty_final=30, harga_beli=12000),
            DetailPesanan(pesanan_id=1, produk_id=3, qty_rekomendasi=5, qty_final=0, harga_beli=7000),
            DetailPesanan(pesanan_id=2, produk_id=1, qty_rekomendasi=5, qty_final=5, harga_beli=9000),
            DetailPesanan(pesanan_id=3, produk_id=4, qty_rekomendasi=5, qty_final=5, harga_beli=9000)])
        sesi.commit()
        yield sesi


def test_terima_membuat_batch_dan_status_diterima(s):
    r = terima_pesanan_di(s, 1, HARI)
    assert r["ok"] is True and len(r["data"]["batch_id"]) == 2   # qty 0 dilewati
    assert s.get(PesananPembelian, 1).status == "diterima"
    b = s.scalars(select(BatchStok).where(BatchStok.produk_id == 1)).one()
    assert b.jumlah_awal == 50 and b.hpp_satuan == 9000
    assert b.tgl_masuk == HARI and b.tgl_kedaluwarsa == date(2027, 2, 28)   # +100 hari
    assert s.scalars(select(MutasiStok).where(MutasiStok.jenis == "masuk")).all().__len__() == 2


def test_terima_update_harga_beli_terakhir(s):
    terima_pesanan_di(s, 1, HARI)
    assert s.get(Produk, 1).harga_beli_terakhir == 9000
    assert s.get(Produk, 2).harga_beli_terakhir == 12000


def test_terima_status_salah_ditolak(s):
    assert terima_pesanan_di(s, 2, HARI)["ok"] is False
    assert terima_pesanan_di(s, 999, HARI)["ok"] is False
    assert s.scalars(select(BatchStok)).all() == []


def test_terima_tanpa_umur_simpan_ditolak_tanpa_batch(s):
    r = terima_pesanan_di(s, 3, HARI)
    assert r["ok"] is False and "Kopi" in r["pesan"]
    assert s.scalars(select(BatchStok)).all() == []
    assert s.get(PesananPembelian, 3).status == "dikirim"


def test_terima_dua_kali_ditolak(s):
    terima_pesanan_di(s, 1, HARI)
    assert terima_pesanan_di(s, 1, HARI)["ok"] is False


def test_teks_wa_berisi_pemasok_usaha_dan_item(s):
    t = get_teks_pesanan_wa_di(s, 1)
    assert "CV Sumber" in t and "Toko Berkah" in t
    assert "1. Beras - 50 kg" in t and "2. Gula - 30 kg" in t
    assert "Teh" not in t   # qty 0 tidak ditulis


def test_teks_wa_pesanan_tidak_ada(s):
    assert get_teks_pesanan_wa_di(s, 999) == "Pesanan tidak ditemukan"
