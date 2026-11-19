"""Tes langkah 1: membaca batch urut FEFO. Memakai SQLite sementara."""
from datetime import date

import pytest

from backend import db
from backend.models import Base, BatchStok, Produk
from backend.penjualan import ambil_batch_fefo


def _batch(produk_id, kedaluwarsa, sisa, status="aktif"):
    return BatchStok(
        produk_id=produk_id, tgl_masuk=date(2026, 11, 1),
        tgl_kedaluwarsa=kedaluwarsa, jumlah_awal=50, jumlah_sisa=sisa,
        hpp_satuan=1000, status=status,
    )


@pytest.fixture
def sesi(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDWISE_DB_URL", f"sqlite:///{tmp_path / 'tes.sqlite'}")
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_SessionLocal", None)
    Base.metadata.create_all(db.get_engine())
    with db.get_session() as s:
        s.add_all([Produk(kode="P1", nama="Susu UHT", harga_jual=5000),
                   Produk(kode="P2", nama="Teh Kotak", harga_jual=4000)])
        s.commit()
        yield s


def test_urut_kedaluwarsa_terdekat_dulu(sesi):
    sesi.add_all([
        _batch(1, date(2027, 2, 1), 50),   # C
        _batch(1, date(2026, 12, 20), 6),  # A
        _batch(1, date(2027, 1, 5), 20),   # B
    ])
    sesi.commit()
    hasil = ambil_batch_fefo(sesi, 1)
    assert [b.tgl_kedaluwarsa for b in hasil] == [
        date(2026, 12, 20), date(2027, 1, 5), date(2027, 2, 1)]


def test_batch_habis_dan_kedaluwarsa_tidak_ikut(sesi):
    sesi.add_all([
        _batch(1, date(2026, 12, 1), 0, "habis"),
        _batch(1, date(2026, 11, 1), 5, "kedaluwarsa"),
        _batch(1, date(2026, 12, 5), 0),           # aktif tapi sisa 0
        _batch(1, date(2027, 1, 1), 10),           # satu-satunya yang valid
    ])
    sesi.commit()
    hasil = ambil_batch_fefo(sesi, 1)
    assert len(hasil) == 1 and hasil[0].jumlah_sisa == 10


def test_produk_lain_tidak_ikut(sesi):
    sesi.add_all([_batch(1, date(2027, 1, 1), 10), _batch(2, date(2026, 12, 1), 10)])
    sesi.commit()
    assert all(b.produk_id == 1 for b in ambil_batch_fefo(sesi, 1))


def test_tanggal_sama_urut_id(sesi):
    sesi.add_all([_batch(1, date(2027, 1, 1), 10), _batch(1, date(2027, 1, 1), 20)])
    sesi.commit()
    hasil = ambil_batch_fefo(sesi, 1)
    assert hasil[0].id < hasil[1].id


def test_tidak_ada_batch_mengembalikan_list_kosong(sesi):
    assert ambil_batch_fefo(sesi, 1) == []
