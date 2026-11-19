from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.input_data import KOLOM_BATCH, get_batch_di
from backend.models import Base, BatchStok, Produk

HARI = date(2026, 11, 18)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add_all([Produk(id=1, kode="P1", nama="Susu"),
                      Produk(id=2, kode="P2", nama="Beras")])
        sesi.commit()
        yield sesi


def _batch(produk_id, kedaluwarsa, sisa=10, status="aktif"):
    return BatchStok(produk_id=produk_id, tgl_masuk=HARI, tgl_kedaluwarsa=kedaluwarsa,
                     jumlah_awal=20, jumlah_sisa=sisa, hpp_satuan=1000, status=status)


def _isi(s):
    s.add_all([
        _batch(1, date(2026, 12, 20)),
        _batch(1, date(2026, 12, 1)),
        _batch(1, date(2026, 11, 20), sisa=0, status="habis"),
        _batch(1, date(2026, 11, 10), status="kedaluwarsa"),
        _batch(2, date(2026, 12, 5)),
    ])
    s.commit()


def test_kolom_lengkap_walau_kosong(s):
    df = get_batch_di(s)
    assert list(df.columns) == KOLOM_BATCH
    assert len(df) == 0


def test_aktif_saja_default_semua_produk(s):
    _isi(s)
    df = get_batch_di(s)
    assert set(df["status"]) == {"aktif"}
    assert len(df) == 3


def test_semua_status_bila_aktif_saja_false(s):
    _isi(s)
    df = get_batch_di(s, aktif_saja=False)
    assert len(df) == 5
    assert set(df["status"]) == {"aktif", "habis", "kedaluwarsa"}


def test_filter_produk(s):
    _isi(s)
    df = get_batch_di(s, produk_id=1)
    assert set(df["produk_id"]) == {1}
    assert len(df) == 2


def test_urutan_fefo(s):
    _isi(s)
    df = get_batch_di(s, produk_id=1)
    assert list(df["tgl_kedaluwarsa"]) == [date(2026, 12, 1), date(2026, 12, 20)]


def test_nama_produk_ikut(s):
    _isi(s)
    df = get_batch_di(s, produk_id=2)
    assert list(df["nama_produk"]) == ["Beras"]


def test_produk_tanpa_batch_kosong_berkolom(s):
    _isi(s)
    s.add(Produk(id=3, kode="P3", nama="Roti"))
    s.commit()
    df = get_batch_di(s, produk_id=3)
    assert len(df) == 0
    assert list(df.columns) == KOLOM_BATCH
