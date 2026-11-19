"""Tes Blok 3: tambah_produk dan simpan_biaya (termasuk tes silang dengan laporan laba)."""
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.input_data import get_produk_di, simpan_biaya_di, tambah_produk_di
from backend.laba import hitung_laba_di
from backend.models import Base, BiayaOperasional, HargaJual, Kategori, Pemasok, Produk


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(Kategori(id=1, nama="Sembako"))
        sesi.add(Pemasok(id=1, nama="Pemasok A", lead_time_hari=4))
        sesi.commit()
        yield sesi


def data(**ubah):
    d = {"kode": "PRD-100", "nama": "Teh Botol", "kategori": "Sembako", "pemasok": "Pemasok A",
         "satuan": "botol", "harga_jual": 5000}
    d.update(ubah)
    return d


# ----------------------------------------------------------- tambah_produk
def test_tambah_produk_minimal(s):
    r = tambah_produk_di(s, data())
    assert r["ok"], r
    p = s.get(Produk, r["data"]["produk_id"])
    assert (p.kode, p.nama, p.kategori_id, p.pemasok_id, p.harga_jual) == ("PRD-100", "Teh Botol", 1, 1, 5000)
    assert p.aktif is True and p.tunda_pesan is False
    assert p.lead_time_hari == 4                         # default dari pemasok
    h = s.execute(select(HargaJual)).scalar_one()
    assert (h.produk_id, h.harga, h.sumber) == (p.id, 5000, "manual")


def test_tambah_produk_opsional_dan_id(s):
    r = tambah_produk_di(s, data(kategori=None, kategori_id=1, pemasok=None, pemasok_id="1",
                                 harga_beli_terakhir="3500", umur_simpan_hari=90, lead_time_hari=7,
                                 tunda_pesan=True))
    assert r["ok"], r
    p = s.get(Produk, r["data"]["produk_id"])
    assert (p.harga_beli_terakhir, p.umur_simpan_hari, p.lead_time_hari) == (3500, 90, 7)
    assert p.tunda_pesan is False                        # milik Wulan, tidak disentuh


def test_tambah_produk_muncul_di_get_produk(s):
    tambah_produk_di(s, data())
    df = get_produk_di(s)
    assert df.iloc[0]["nama_produk"] == "Teh Botol" and df.iloc[0]["kategori"] == "Sembako"


def test_kode_ganda_ditolak_tanpa_beda_huruf(s):
    assert tambah_produk_di(s, data())["ok"]
    r = tambah_produk_di(s, data(nama="Lain", kode="prd-100"))
    assert not r["ok"] and "sudah dipakai" in r["pesan"]
    assert len(s.execute(select(Produk)).scalars().all()) == 1


@pytest.mark.parametrize("ubah", [
    {"kode": ""}, {"nama": None}, {"satuan": " "}, {"harga_jual": ""}, {"harga_jual": -1},
    {"harga_jual": "murah"}, {"harga_jual": 1.5}, {"kategori": "Tidak Ada"}, {"pemasok": "Tidak Ada"},
    {"kategori": None}, {"umur_simpan_hari": -3}, {"lead_time_hari": "x"},
])
def test_tambah_produk_input_salah(s, ubah):
    assert tambah_produk_di(s, data(**ubah))["ok"] is False
    assert s.execute(select(Produk)).scalars().all() == []
    assert s.execute(select(HargaJual)).scalars().all() == []


def test_tambah_produk_bukan_dict(s):
    assert not tambah_produk_di(s, "x")["ok"] and not tambah_produk_di(s, None)["ok"]


# ------------------------------------------------------------- simpan_biaya
def test_simpan_biaya_dan_dibaca_laporan_laba(s):
    assert simpan_biaya_di(s, date(2026, 11, 3), "Listrik", 450000, "Tagihan")["ok"]
    assert simpan_biaya_di(s, "2026-11-20", "Gaji", "1000000")["ok"]
    assert simpan_biaya_di(s, date(2026, 12, 1), "Sewa", 700000)["ok"]     # luar periode
    b = s.execute(select(BiayaOperasional).order_by(BiayaOperasional.id)).scalars().all()
    assert (b[0].kategori_biaya, b[0].jumlah, b[0].keterangan) == ("Listrik", 450000, "Tagihan")
    assert b[1].keterangan is None
    laba = hitung_laba_di(s, date(2026, 11, 1), date(2026, 11, 30))
    assert laba["Biaya Operasional"] == 1450000 and laba["Laba Bersih"] == -1450000


@pytest.mark.parametrize("args", [
    ("bukan tanggal", "Listrik", 1000), (date(2026, 11, 3), "", 1000),
    (date(2026, 11, 3), "  ", 1000), (date(2026, 11, 3), "Listrik", 0),
    (date(2026, 11, 3), "Listrik", -5), (date(2026, 11, 3), "Listrik", "abc"),
    (date(2026, 11, 3), "Listrik", 10.5), (date(2026, 11, 3), "Listrik", True),
])
def test_simpan_biaya_input_salah(s, args):
    assert simpan_biaya_di(s, *args)["ok"] is False
    assert s.execute(select(BiayaOperasional)).scalars().all() == []
