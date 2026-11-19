import pytest
from datetime import date
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.models import Base, Notifikasi, Pemasok, PesananPembelian
from backend.pembelian import simpan_jadwal_kirim_di

HARI = date(2026, 11, 17)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(Pemasok(id=1, nama="Pemasok A", lead_time_hari=3))
        sesi.add_all([PesananPembelian(id=1, pemasok_id=1, tanggal=HARI, status="dipesan"),
                      PesananPembelian(id=2, pemasok_id=1, tanggal=HARI, status="draf")])
        sesi.commit()
        yield sesi


def test_jadwal_disimpan_status_jadi_dikirim(s):
    r = simpan_jadwal_kirim_di(s, 1, date(2026, 11, 20))
    assert r["ok"] is True
    p = s.get(PesananPembelian, 1)
    assert p.status == "dikirim" and p.jadwal_kirim == date(2026, 11, 20)


def test_notifikasi_pesanan_dikirim_tercatat(s):
    simpan_jadwal_kirim_di(s, 1, date(2026, 11, 20))
    n = s.scalars(select(Notifikasi)).one()
    assert n.jenis == "pesanan_dikirim" and n.level == "info"
    assert n.ref_tabel == "pesanan_pembelian" and n.ref_id == 1


def test_pesanan_draf_ditolak_dan_tanpa_notifikasi(s):
    assert simpan_jadwal_kirim_di(s, 2, date(2026, 11, 20))["ok"] is False
    assert s.scalars(select(Notifikasi)).all() == []


def test_tanggal_sebelum_tanggal_pesanan_ditolak(s):
    assert simpan_jadwal_kirim_di(s, 1, date(2026, 11, 10))["ok"] is False
    assert s.get(PesananPembelian, 1).status == "dipesan"


def test_tanggal_bukan_date_dan_pesanan_tidak_ada(s):
    assert simpan_jadwal_kirim_di(s, 1, "2026-11-20")["ok"] is False
    assert simpan_jadwal_kirim_di(s, 999, date(2026, 11, 20))["ok"] is False


def test_dua_kali_ditolak(s):
    simpan_jadwal_kirim_di(s, 1, date(2026, 11, 20))
    assert simpan_jadwal_kirim_di(s, 1, date(2026, 11, 21))["ok"] is False
