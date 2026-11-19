import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.input_data import KOLOM_PRODUK, get_produk_di
from backend.models import Base, Kategori, Pemasok, Produk


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        yield sesi


def _isi(s):
    s.add(Kategori(id=1, nama="Sembako"))
    s.add(Pemasok(id=1, nama="Pemasok A", lead_time_hari=3))
    s.add_all([
        Produk(id=1, kode="P1", nama="Susu", kategori_id=1, pemasok_id=1,
               satuan="dus", harga_jual=12000, aktif=True),
        Produk(id=2, kode="P2", nama="Beras", kategori_id=1, pemasok_id=1, aktif=True),
        Produk(id=3, kode="P3", nama="Roti", aktif=False),
        Produk(id=4, kode="P4", nama="Gula", aktif=True),  # tanpa kategori dan pemasok
    ])
    s.commit()


def test_kolom_lengkap_walau_kosong(s):
    df = get_produk_di(s)
    assert list(df.columns) == KOLOM_PRODUK
    assert len(df) == 0


def test_aktif_saja_default(s):
    _isi(s)
    df = get_produk_di(s)
    assert set(df["kode"]) == {"P1", "P2", "P4"}


def test_semua_produk_termasuk_nonaktif(s):
    _isi(s)
    df = get_produk_di(s, aktif_saja=False)
    assert set(df["kode"]) == {"P1", "P2", "P3", "P4"}


def test_urut_menurut_nama(s):
    _isi(s)
    assert list(get_produk_di(s)["nama_produk"]) == ["Beras", "Gula", "Susu"]


def test_kategori_dan_pemasok_berupa_nama(s):
    _isi(s)
    susu = get_produk_di(s).set_index("kode").loc["P1"]
    assert susu["kategori"] == "Sembako"
    assert susu["pemasok"] == "Pemasok A"
    assert susu["harga_jual"] == 12000


def test_produk_tanpa_kategori_dan_pemasok_tetap_muncul(s):
    _isi(s)
    gula = get_produk_di(s).set_index("kode").loc["P4"]
    assert gula["kategori"] is None or gula["kategori"] != gula["kategori"]
    assert gula["pemasok"] is None or gula["pemasok"] != gula["pemasok"]
