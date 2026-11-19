from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.input_data import KOLOM_NOTIF, get_notifikasi_di
from backend.models import Base, Notifikasi


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        yield sesi


def _notif(judul, jam, dibaca=False, level="info"):
    return Notifikasi(jenis="uji", level=level, judul=judul, pesan="isi", dibaca=dibaca,
                      dibuat_pada=datetime(2026, 11, 18, jam, 0))


def _isi(s):
    s.add_all([_notif("lama", 8, dibaca=True),
               _notif("tengah", 10),
               _notif("baru", 12, level="kritis")])
    s.commit()


def test_kolom_lengkap_walau_kosong(s):
    df = get_notifikasi_di(s)
    assert list(df.columns) == KOLOM_NOTIF
    assert len(df) == 0


def test_semua_notifikasi_default(s):
    _isi(s)
    assert len(get_notifikasi_di(s)) == 3


def test_terbaru_di_atas(s):
    _isi(s)
    assert list(get_notifikasi_di(s)["judul"]) == ["baru", "tengah", "lama"]


def test_belum_dibaca_saja(s):
    _isi(s)
    df = get_notifikasi_di(s, belum_dibaca=True)
    assert list(df["judul"]) == ["baru", "tengah"]
    assert not df["dibaca"].any()


def test_waktu_sama_urut_id_terbaru(s):
    s.add_all([_notif("a", 9), _notif("b", 9)])
    s.commit()
    assert list(get_notifikasi_di(s)["judul"]) == ["b", "a"]


def test_isi_kolom(s):
    _isi(s)
    baris = get_notifikasi_di(s).iloc[0]
    assert baris["level"] == "kritis"
    assert baris["jenis"] == "uji"
    assert baris["pesan"] == "isi"
    assert baris["notif_id"] == 3
