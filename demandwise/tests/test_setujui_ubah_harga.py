import pytest
from datetime import date
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.harga import (hitung_rekomendasi_harga, setujui_harga, setujui_harga_di,
                           ubah_harga_manual, ubah_harga_manual_di)
from backend.models import Base, HargaJual, Produk

HARI_INI = date(2026, 11, 18)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(Produk(id=1, kode="P1", nama="Beras", harga_beli_terakhir=7500, harga_jual=9000))
        sesi.add(Produk(id=2, kode="P2", nama="Gula", harga_beli_terakhir=None, harga_jual=15000))
        sesi.add(Produk(id=3, kode="P3", nama="Teh", harga_beli_terakhir=5000, aktif=False))
        sesi.commit()
        yield sesi


def _riwayat(s, pid):
    return s.scalars(select(HargaJual).where(HargaJual.produk_id == pid)
                     .order_by(HargaJual.id)).all()


# --- setujui_harga ---------------------------------------------------------
def test_setujui_menerapkan_harga_rekomendasi(s):
    rekom = int(hitung_rekomendasi_harga(s, HARI_INI).set_index("produk_id")
                .loc[1, "harga_rekomendasi"])
    h = setujui_harga_di(s, 1, HARI_INI)
    assert h["ok"] and h["data"]["diubah"] and h["data"]["harga_baru"] == rekom
    assert h["data"]["harga_lama"] == 9000
    assert s.get(Produk, 1).harga_jual == rekom
    r = _riwayat(s, 1)
    assert len(r) == 1 and r[0].harga == rekom
    assert r[0].sumber == "rekomendasi" and r[0].berlaku_mulai == HARI_INI


def test_setujui_dua_kali_tidak_menambah_riwayat(s):
    setujui_harga_di(s, 1, HARI_INI)
    h = setujui_harga_di(s, 1, HARI_INI)
    assert h["ok"] and not h["data"]["diubah"]
    assert len(_riwayat(s, 1)) == 1


def test_setujui_ditolak_tanpa_hpp(s):
    h = setujui_harga_di(s, 2, HARI_INI)
    assert not h["ok"] and "HPP" in h["pesan"]
    assert s.get(Produk, 2).harga_jual == 15000 and _riwayat(s, 2) == []


def test_setujui_ditolak_produk_tidak_ada_atau_nonaktif(s):
    assert not setujui_harga_di(s, 99, HARI_INI)["ok"]
    h = setujui_harga_di(s, 3, HARI_INI)
    assert not h["ok"] and "tidak aktif" in h["pesan"]


# --- ubah_harga_manual -----------------------------------------------------
def test_manual_diterima_dan_tercatat(s):
    h = ubah_harga_manual_di(s, 1, 9500, HARI_INI)
    assert h["ok"] and h["data"]["harga_baru"] == 9500
    assert h["data"]["margin_persen"] == round((9500 - 7500) / 9500 * 100, 1)
    assert s.get(Produk, 1).harga_jual == 9500
    r = _riwayat(s, 1)
    assert len(r) == 1 and r[0].sumber == "manual"


def test_manual_tepat_di_batas_margin_minimum_diterima(s):
    # HPP 7.500 / 0,85 = 8.823,5 -> 8.824 sudah di atas 15%
    assert ubah_harga_manual_di(s, 1, 8824, HARI_INI)["ok"]


def test_manual_di_bawah_margin_minimum_ditolak_tanpa_perubahan(s):
    h = ubah_harga_manual_di(s, 1, 8800, HARI_INI)
    assert not h["ok"] and "margin minimum" in h["pesan"]
    assert "9.000" in h["pesan"]            # saran harga minimal (dibulatkan 500)
    assert s.get(Produk, 1).harga_jual == 9000 and _riwayat(s, 1) == []


@pytest.mark.parametrize("harga", [0, -100, 9500.5, "9500", None, True])
def test_manual_harga_tidak_valid_ditolak(s, harga):
    h = ubah_harga_manual_di(s, 1, harga, HARI_INI)
    assert not h["ok"]
    assert s.get(Produk, 1).harga_jual == 9000 and _riwayat(s, 1) == []


def test_manual_ditolak_tanpa_hpp_atau_produk_salah(s):
    assert "HPP" in ubah_harga_manual_di(s, 2, 20000, HARI_INI)["pesan"]
    assert not ubah_harga_manual_di(s, 99, 20000, HARI_INI)["ok"]
    assert "tidak aktif" in ubah_harga_manual_di(s, 3, 20000, HARI_INI)["pesan"]


def test_pembungkus_tidak_melempar_error(monkeypatch):
    import backend.db as db

    def rusak():
        raise RuntimeError("database mati")
    monkeypatch.setattr(db, "get_session", rusak)
    for h in (setujui_harga(1), ubah_harga_manual(1, 9500)):
        assert h["ok"] is False and "Gagal" in h["pesan"]
