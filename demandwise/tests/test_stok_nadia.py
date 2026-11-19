"""Tes Blok 2: catat_retur, catat_barang_rusak, catat_writeoff, simpan_opname."""
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.input_data import (catat_barang_rusak_di, catat_retur_di, catat_writeoff_di,
                                get_notifikasi_di, simpan_opname_di)
from backend.models import (Base, BatchStok, Kategori, MutasiStok, Pemasok, Produk,
                            StockOpname, Writeoff)

T = date(2026, 11, 10)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(Kategori(id=1, nama="Sembako"))
        sesi.add(Pemasok(id=1, nama="A", lead_time_hari=2))
        sesi.add_all([Produk(id=1, kode="P1", nama="Susu", kategori_id=1, pemasok_id=1,
                             harga_jual=12000),
                      Produk(id=2, kode="P2", nama="Beras", kategori_id=1, pemasok_id=1,
                             harga_jual=9000)])
        # Produk 1: batch 1 kedaluwarsa lebih dekat (10), batch 2 lebih jauh dan lebih baru (20)
        sesi.add_all([
            BatchStok(id=1, produk_id=1, tgl_masuk=date(2026, 10, 1), tgl_kedaluwarsa=date(2026, 12, 1),
                      jumlah_awal=10, jumlah_sisa=10, hpp_satuan=8000, status="aktif"),
            BatchStok(id=2, produk_id=1, tgl_masuk=date(2026, 11, 1), tgl_kedaluwarsa=date(2027, 3, 1),
                      jumlah_awal=20, jumlah_sisa=20, hpp_satuan=9000, status="aktif"),
        ])
        sesi.commit()
        yield sesi


def sisa(s, bid):
    return s.get(BatchStok, bid).jumlah_sisa


def mutasi(s, jenis):
    return list(s.execute(select(MutasiStok).where(MutasiStok.jenis == jenis)
                          .order_by(MutasiStok.id)).scalars())


# ------------------------------------------------------------ catat_retur
def test_retur_mengurangi_fefo_dan_mutasi_negatif(s):
    r = catat_retur_di(s, 1, 14, "Kemasan rusak", T)
    assert r["ok"], r
    assert (sisa(s, 1), sisa(s, 2)) == (0, 16)
    assert s.get(BatchStok, 1).status == "habis"
    m = mutasi(s, "retur")
    assert [(x.batch_id, x.qty) for x in m] == [(1, -10), (2, -4)]
    assert r["data"]["batch"] == [{"batch_id": 1, "qty": 10}, {"batch_id": 2, "qty": 4}]


def test_retur_stok_kurang_tidak_menulis_apa_pun(s):
    r = catat_retur_di(s, 1, 31, "x", T)
    assert not r["ok"] and "tidak cukup" in r["pesan"]
    assert (sisa(s, 1), sisa(s, 2)) == (10, 20) and mutasi(s, "retur") == []


@pytest.mark.parametrize("args", [
    (1, 0, "k", T), (1, -2, "k", T), (1, 2.5, "k", T), (1, True, "k", T), (1, "abc", "k", T),
    (1, 2, "", T), (1, 2, "   ", T), (1, 2, "k", "bukan tanggal"), (99, 2, "k", T), ("x", 2, "k", T),
])
def test_retur_input_salah(s, args):
    assert catat_retur_di(s, *args)["ok"] is False
    assert mutasi(s, "retur") == []


def test_retur_produk_tanpa_batch(s):
    r = catat_retur_di(s, 2, 1, "k", T)
    assert not r["ok"] and "tidak cukup" in r["pesan"]


# ------------------------------------------------------ catat_barang_rusak
def test_rusak_mengurangi_batch_terpilih(s):
    r = catat_barang_rusak_di(s, 1, 2, 5, "Penyok", T)
    assert r["ok"] and sisa(s, 2) == 15 and sisa(s, 1) == 10
    assert [(x.batch_id, x.qty) for x in mutasi(s, "rusak")] == [(2, -5)]


def test_rusak_semua_jadi_habis(s):
    assert catat_barang_rusak_di(s, 1, 1, 10, "Banjir", T)["ok"]
    assert s.get(BatchStok, 1).status == "habis"


def test_rusak_validasi(s):
    assert not catat_barang_rusak_di(s, 1, 1, 11, "k", T)["ok"]       # melebihi sisa
    assert not catat_barang_rusak_di(s, 2, 1, 1, "k", T)["ok"]        # batch bukan milik produk
    assert not catat_barang_rusak_di(s, 1, 99, 1, "k", T)["ok"]       # batch tidak ada
    assert not catat_barang_rusak_di(s, 1, 1, 0, "k", T)["ok"]
    assert not catat_barang_rusak_di(s, 1, 1, 1, "", T)["ok"]
    assert sisa(s, 1) == 10 and mutasi(s, "rusak") == []


def test_rusak_batch_habis_ditolak(s):
    catat_barang_rusak_di(s, 1, 1, 10, "k", T)
    r = catat_barang_rusak_di(s, 1, 1, 1, "k", T)
    assert not r["ok"] and "habis" in r["pesan"]


# ---------------------------------------------------------- catat_writeoff
def test_writeoff_lengkap(s):
    r = catat_writeoff_di(s, 1, 4, T)
    assert r["ok"], r
    assert r["data"]["total_rugi"] == 4 * 8000 and sisa(s, 1) == 6
    w = s.execute(select(Writeoff)).scalar_one()
    assert (w.batch_id, w.produk_id, w.qty, w.hpp_satuan, w.total_rugi) == (1, 1, 4, 8000, 32000)
    assert [(x.batch_id, x.qty) for x in mutasi(s, "writeoff")] == [(1, -4)]
    n = get_notifikasi_di(s)
    assert len(n) == 1
    assert n.iloc[0]["jenis"] == "writeoff_dicatat" and n.iloc[0]["level"] == "info"
    assert n.iloc[0]["ref_tabel"] == "writeoff" and n.iloc[0]["ref_id"] == w.id
    assert "32.000" in n.iloc[0]["pesan"]


def test_writeoff_habis_dan_validasi(s):
    assert catat_writeoff_di(s, 1, 10, T)["ok"] and s.get(BatchStok, 1).status == "habis"
    assert not catat_writeoff_di(s, 1, 1, T)["ok"]       # sudah habis
    assert not catat_writeoff_di(s, 2, 21, T)["ok"]      # melebihi sisa
    assert not catat_writeoff_di(s, 99, 1, T)["ok"]
    assert not catat_writeoff_di(s, 2, 0, T)["ok"]
    assert len(s.execute(select(Writeoff)).scalars().all()) == 1
    assert len(get_notifikasi_di(s)) == 1


def test_writeoff_mempengaruhi_laba(s):
    from backend.laba import hitung_laba_di
    catat_writeoff_di(s, 1, 4, T)
    assert hitung_laba_di(s, date(2026, 11, 1), date(2026, 11, 30))[
        "Kerugian Kedaluwarsa (Write-off)"] == 32000


# ------------------------------------------------------------ simpan_opname
def test_opname_selisih_negatif_fefo(s):
    r = simpan_opname_di(s, T, [{"produk_id": 1, "stok_fisik": 25}])   # sistem 30 -> -5
    assert r["ok"], r
    assert r["data"]["hasil"] == [{"produk_id": 1, "stok_sistem": 30, "stok_fisik": 25, "selisih": -5}]
    assert (sisa(s, 1), sisa(s, 2)) == (5, 20)
    o = s.execute(select(StockOpname)).scalar_one()
    assert (o.stok_sistem, o.stok_fisik, o.selisih) == (30, 25, -5)
    assert [(x.batch_id, x.qty) for x in mutasi(s, "opname")] == [(1, -5)]


def test_opname_negatif_melewati_batch(s):
    simpan_opname_di(s, T, [{"produk_id": 1, "stok_fisik": 12}])       # -18
    assert (sisa(s, 1), sisa(s, 2)) == (0, 12) and s.get(BatchStok, 1).status == "habis"


def test_opname_selisih_positif_ke_batch_terbaru(s):
    r = simpan_opname_di(s, T, [{"produk_id": 1, "stok_fisik": 33}])
    assert r["ok"] and (sisa(s, 1), sisa(s, 2)) == (10, 23)
    assert [(x.batch_id, x.qty) for x in mutasi(s, "opname")] == [(2, 3)]


def test_opname_selisih_nol_dicatat_tanpa_mutasi(s):
    r = simpan_opname_di(s, T, [{"produk_id": 1, "stok_fisik": 30}])
    assert r["ok"] and mutasi(s, "opname") == []
    assert s.execute(select(StockOpname)).scalar_one().selisih == 0


def test_opname_semua_atau_tidak_sama_sekali(s):
    r = simpan_opname_di(s, T, [{"produk_id": 1, "stok_fisik": 5}, {"produk_id": 99, "stok_fisik": 1}])
    assert not r["ok"]
    s.rollback()
    assert (sisa(s, 1), sisa(s, 2)) == (10, 20)
    assert s.execute(select(StockOpname)).scalars().all() == []


def test_opname_produk_tanpa_batch_dan_kelebihan(s):
    r = simpan_opname_di(s, T, [{"produk_id": 2, "stok_fisik": 3}])
    assert not r["ok"] and "tidak ada batch aktif" in r["pesan"]


@pytest.mark.parametrize("items", [
    [], None, "x", [{"produk_id": 1}], [{"stok_fisik": 1}],
    [{"produk_id": 1, "stok_fisik": -1}], [{"produk_id": 1, "stok_fisik": 2.5}],
    [{"produk_id": 1, "stok_fisik": 1}, {"produk_id": 1, "stok_fisik": 2}],
])
def test_opname_input_salah(s, items):
    assert simpan_opname_di(s, T, items)["ok"] is False


def test_opname_tanggal_salah(s):
    assert not simpan_opname_di(s, "kemarin", [{"produk_id": 1, "stok_fisik": 1}])["ok"]
