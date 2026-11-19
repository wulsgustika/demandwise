import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import Base, DetailPesanan, Pemasok, PesananPembelian, Produk
from backend.pembelian import revisi_pesanan_di, setujui_pesanan_di


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(Pemasok(id=1, nama="Pemasok A", lead_time_hari=3))
        sesi.add_all([Produk(id=1, kode="P1", nama="Beras", pemasok_id=1),
                      Produk(id=2, kode="P2", nama="Gula", pemasok_id=1)])
        sesi.add(PesananPembelian(id=1, pemasok_id=1, tanggal=date(2026, 11, 17), status="draf"))
        sesi.add_all([
            DetailPesanan(pesanan_id=1, produk_id=1, qty_rekomendasi=50, qty_final=50, harga_beli=9000),
            DetailPesanan(pesanan_id=1, produk_id=2, qty_rekomendasi=30, qty_final=30, harga_beli=12000)])
        sesi.add(PesananPembelian(id=2, pemasok_id=1, tanggal=date(2026, 11, 17), status="draf"))
        sesi.commit()
        yield sesi


def _qty(s, pid):
    return s.query(DetailPesanan).filter_by(pesanan_id=1, produk_id=pid).one().qty_final


def test_setujui_ubah_status_jadi_dipesan(s):
    r = setujui_pesanan_di(s, 1)
    assert r["ok"] is True
    assert s.get(PesananPembelian, 1).status == "dipesan"


def test_setujui_dua_kali_ditolak(s):
    setujui_pesanan_di(s, 1)
    r = setujui_pesanan_di(s, 1)
    assert r["ok"] is False


def test_setujui_pesanan_tidak_ada(s):
    assert setujui_pesanan_di(s, 999)["ok"] is False


def test_setujui_pesanan_kosong_ditolak(s):
    assert setujui_pesanan_di(s, 2)["ok"] is False


def test_revisi_ubah_qty_final_saja(s):
    r = revisi_pesanan_di(s, 1, [{"produk_id": 1, "qty_final": 40}])
    assert r["ok"] is True
    assert _qty(s, 1) == 40
    assert _qty(s, 2) == 30
    d = s.query(DetailPesanan).filter_by(pesanan_id=1, produk_id=1).one()
    assert d.qty_rekomendasi == 50   # angka rekomendasi tidak berubah


def test_revisi_satu_salah_tidak_ada_yang_berubah(s):
    r = revisi_pesanan_di(s, 1, [{"produk_id": 1, "qty_final": 40},
                                 {"produk_id": 2, "qty_final": -5}])
    assert r["ok"] is False
    assert _qty(s, 1) == 50 and _qty(s, 2) == 30


def test_revisi_produk_tidak_ada_di_pesanan(s):
    assert revisi_pesanan_di(s, 1, [{"produk_id": 99, "qty_final": 5}])["ok"] is False


def test_revisi_setelah_disetujui_ditolak(s):
    setujui_pesanan_di(s, 1)
    assert revisi_pesanan_di(s, 1, [{"produk_id": 1, "qty_final": 40}])["ok"] is False
    assert _qty(s, 1) == 50


def test_revisi_qty_bukan_bilangan_bulat(s):
    assert revisi_pesanan_di(s, 1, [{"produk_id": 1, "qty_final": 2.5}])["ok"] is False
    assert revisi_pesanan_di(s, 1, [])["ok"] is False
