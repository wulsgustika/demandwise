import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.input_data import get_notifikasi_di, tandai_dibaca_di
from backend.models import Base, Notifikasi


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add_all([Notifikasi(id=1, jenis="uji", level="info", judul="satu"),
                      Notifikasi(id=2, jenis="uji", level="info", judul="dua")])
        sesi.commit()
        yield sesi


def test_tandai_satu_notifikasi(s):
    hasil = tandai_dibaca_di(s, 1)
    assert hasil["ok"] is True
    assert hasil["data"] == {"notif_id": 1}
    assert s.get(Notifikasi, 1).dibaca is True


def test_notifikasi_lain_tidak_berubah(s):
    tandai_dibaca_di(s, 1)
    assert s.get(Notifikasi, 2).dibaca is False


def test_hilang_dari_daftar_belum_dibaca(s):
    tandai_dibaca_di(s, 1)
    s.commit()
    assert list(get_notifikasi_di(s, belum_dibaca=True)["notif_id"]) == [2]


def test_dipanggil_dua_kali_tetap_ok(s):
    tandai_dibaca_di(s, 1)
    hasil = tandai_dibaca_di(s, 1)
    assert hasil["ok"] is True
    assert "sudah" in hasil["pesan"]


def test_id_tidak_ada(s):
    hasil = tandai_dibaca_di(s, 99)
    assert hasil["ok"] is False
    assert hasil["data"] is None


@pytest.mark.parametrize("salah", ["1", None, 1.5, True])
def test_id_bukan_bilangan_bulat(s, salah):
    hasil = tandai_dibaca_di(s, salah)
    assert hasil["ok"] is False
    assert s.get(Notifikasi, 1).dibaca is False
