import pytest
from datetime import date
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.models import Base, BatchStok, MutasiStok, Notifikasi, Produk
from backend.notifikasi import kirim_notifikasi_di
from backend.stok import catat_barang_masuk_di

HARI = date(2026, 11, 18)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(Produk(id=1, kode="P1", nama="Beras"))
        sesi.commit()
        yield sesi


def test_barang_masuk_buat_batch_dan_mutasi_positif(s):
    r = catat_barang_masuk_di(s, 1, 50, date(2027, 1, 1), 9000, HARI)
    assert r["ok"] is True
    b = s.get(BatchStok, r["data"]["batch_id"])
    assert (b.jumlah_awal, b.jumlah_sisa, b.status, b.hpp_satuan) == (50, 50, "aktif", 9000)
    m = s.scalars(select(MutasiStok)).one()
    assert m.jenis == "masuk" and m.qty == 50 and m.batch_id == b.id


@pytest.mark.parametrize("kw", [
    dict(produk_id=99), dict(qty=0), dict(qty=2.5), dict(hpp_satuan=-1),
    dict(tgl_kedaluwarsa=date(2026, 1, 1)), dict(tanggal="2026-11-18")])
def test_barang_masuk_input_salah_tidak_menyimpan(s, kw):
    arg = dict(produk_id=1, qty=10, tgl_kedaluwarsa=date(2027, 1, 1), hpp_satuan=9000, tanggal=HARI)
    arg.update(kw)
    assert catat_barang_masuk_di(s, **arg)["ok"] is False
    assert s.scalars(select(BatchStok)).all() == []
    assert s.scalars(select(MutasiStok)).all() == []


def test_notifikasi_tersimpan(s):
    r = kirim_notifikasi_di(s, "pesanan_dikirim", "info", "Judul", "Isi", "pesanan_pembelian", 3)
    assert r["ok"] is True
    n = s.scalars(select(Notifikasi)).one()
    assert n.dibaca is False and n.ref_id == 3


def test_notifikasi_level_salah_ditolak(s):
    assert kirim_notifikasi_di(s, "x", "gawat", "Judul", "Isi")["ok"] is False
    assert s.scalars(select(Notifikasi)).all() == []
