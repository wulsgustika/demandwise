"""Tes Blok 4: impor_csv (produk, stok_awal, penjualan), semua-atau-tidak-sama-sekali."""
import io
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.input_data import impor_csv_di
from backend.models import (Base, BatchStok, DetailPenjualan, Kategori, MutasiStok, Pemasok,
                            Produk, TransaksiPenjualan)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(Kategori(id=1, nama="Sembako"))
        sesi.add(Pemasok(id=1, nama="Pemasok A", lead_time_hari=3))
        sesi.add_all([Produk(id=1, kode="P1", nama="Susu", kategori_id=1, pemasok_id=1, harga_jual=12000),
                      Produk(id=2, kode="P2", nama="Beras", kategori_id=1, pemasok_id=1, harga_jual=9000)])
        sesi.commit()
        yield sesi


def csv(teks):
    return io.StringIO(teks)


def jumlah(s, model):
    return len(s.execute(select(model)).scalars().all())


# ------------------------------------------------------------------ produk
def test_impor_produk(s):
    r = impor_csv_di(s, "produk", csv(
        "kode,nama,kategori,pemasok,satuan,harga_jual,harga_beli_terakhir\n"
        "N1,Kopi,Sembako,Pemasok A,sachet,2500,2000\n"
        "N2,Teh,sembako,pemasok a,dus,30000,\n"))
    assert r["ok"] and r["data"]["jumlah_baris"] == 2, r
    assert jumlah(s, Produk) == 4
    assert s.execute(select(Produk).where(Produk.kode == "N1")).scalar_one().harga_beli_terakhir == 2000


def test_impor_produk_ada_error_batal_semua(s):
    r = impor_csv_di(s, "produk", csv(
        "kode,nama,kategori,pemasok,satuan,harga_jual\n"
        "N1,Kopi,Sembako,Pemasok A,sachet,2500\n"
        "P1,Duplikat,Sembako,Pemasok A,dus,100\n"
        "N3,Teh,Tidak Ada,Pemasok A,dus,100\n"))
    assert not r["ok"]
    assert [g["baris"] for g in r["data"]["gagal"]] == [3, 4]
    s.rollback()
    assert jumlah(s, Produk) == 2


# --------------------------------------------------------------- stok_awal
def test_impor_stok_awal_membuat_batch_dan_mutasi(s):
    r = impor_csv_di(s, "stok_awal", csv(
        "kode,qty,tgl_kedaluwarsa,hpp_satuan,tanggal\n"
        "P1,50,2027-01-31,8000,2026-11-01\n"
        "P2,20,2027-02-28,6000,2026-11-01\n"))
    assert r["ok"], r
    b = s.execute(select(BatchStok).order_by(BatchStok.id)).scalars().all()
    assert [(x.produk_id, x.jumlah_sisa, x.hpp_satuan, x.status) for x in b] == [
        (1, 50, 8000, "aktif"), (2, 20, 6000, "aktif")]
    assert [(m.jenis, m.qty) for m in s.execute(select(MutasiStok)).scalars()] == [("masuk", 50), ("masuk", 20)]


def test_impor_stok_awal_pakai_produk_id(s):
    r = impor_csv_di(s, "stok_awal", csv("produk_id,qty,tgl_kedaluwarsa,hpp_satuan\n1,5,2027-01-01,100\n"))
    assert r["ok"] and jumlah(s, BatchStok) == 1


def test_impor_stok_awal_error_batal_semua(s):
    r = impor_csv_di(s, "stok_awal", csv(
        "kode,qty,tgl_kedaluwarsa,hpp_satuan,tanggal\n"
        "P1,50,2027-01-31,8000,2026-11-01\n"
        "XX,5,2027-01-31,100,2026-11-01\n"
        "P2,abc,2027-01-31,100,2026-11-01\n"
        "P2,5,2020-01-01,100,2026-11-01\n"))
    assert not r["ok"] and [g["baris"] for g in r["data"]["gagal"]] == [3, 4, 5]
    s.rollback()
    assert jumlah(s, BatchStok) == 0 and jumlah(s, MutasiStok) == 0


# --------------------------------------------------------------- penjualan
def _stok(s):
    impor_csv_di(s, "stok_awal", csv(
        "kode,qty,tgl_kedaluwarsa,hpp_satuan,tanggal\n"
        "P1,10,2026-12-01,8000,2026-10-01\n"
        "P1,20,2027-03-01,9000,2026-11-01\n"
        "P2,5,2027-03-01,6000,2026-11-01\n"))
    s.commit()


def test_impor_penjualan_lewat_fefo(s):
    _stok(s)
    r = impor_csv_di(s, "penjualan", csv(
        "tanggal,kode,qty\n2026-11-10,P1,12\n2026-11-10,P2,2\n2026-11-11,P1,1\n"))
    assert r["ok"] and r["data"]["jumlah_baris"] == 3, r
    sisa = {b.id: b.jumlah_sisa for b in s.execute(select(BatchStok)).scalars()}
    assert sisa == {1: 0, 2: 17, 3: 3}              # batch 1 habis dulu (FEFO), lalu batch 2
    assert s.get(BatchStok, 1).status == "habis"
    assert jumlah(s, TransaksiPenjualan) == 2       # satu transaksi per tanggal
    d = s.execute(select(DetailPenjualan).order_by(DetailPenjualan.id)).scalars().all()
    assert [(x.batch_id, x.qty, x.harga_satuan, x.hpp_satuan) for x in d[:2]] == [
        (1, 10, 12000, 8000), (2, 2, 12000, 9000)]
    assert sum(m.qty for m in s.execute(select(MutasiStok).where(MutasiStok.jenis == "penjualan")).scalars()) == -15


def test_impor_penjualan_stok_kurang_batal_semua(s):
    _stok(s)
    r = impor_csv_di(s, "penjualan", csv(
        "tanggal,kode,qty\n2026-11-10,P1,5\n2026-11-11,P2,6\n"))
    assert not r["ok"] and "Stok" in r["data"]["gagal"][0]["pesan"]
    s.rollback()
    assert jumlah(s, TransaksiPenjualan) == 0
    assert {b.id: b.jumlah_sisa for b in s.execute(select(BatchStok)).scalars()} == {1: 10, 2: 20, 3: 5}


def test_impor_penjualan_baris_rusak(s):
    _stok(s)
    r = impor_csv_di(s, "penjualan", csv(
        "tanggal,kode,qty\nbukan,P1,1\n2026-11-10,XX,1\n2026-11-10,P1,0\n2026-11-10,P1,1\n"))
    assert not r["ok"] and [g["baris"] for g in r["data"]["gagal"]] == [2, 3, 4]
    s.rollback()
    assert jumlah(s, TransaksiPenjualan) == 0


# ------------------------------------------------------------- umum / format
def test_jenis_salah_dan_kolom_kurang(s):
    assert not impor_csv_di(s, "lain", csv("a\n1\n"))["ok"]
    r = impor_csv_di(s, "penjualan", csv("tanggal,qty\n2026-11-10,1\n"))
    assert not r["ok"] and "kode" in r["pesan"]
    r = impor_csv_di(s, "produk", csv("kode,nama\nA,B\n"))
    assert not r["ok"] and "kategori" in r["pesan"]


def test_csv_kosong_dan_tanpa_data(s):
    assert not impor_csv_di(s, "produk", csv(""))["ok"]
    assert not impor_csv_di(s, "penjualan", csv("tanggal,kode,qty\n"))["ok"]


def test_bisa_dari_path_bytes_dan_titik_koma(s, tmp_path):
    f = tmp_path / "p.csv"
    f.write_text("tanggal;kode;qty\n", encoding="utf-8")
    assert not impor_csv_di(s, "penjualan", str(f))["ok"]          # terbaca, tapi kosong
    b = "﻿kode,qty,tgl_kedaluwarsa,hpp_satuan\nP1,5,2027-01-01,100\n".encode("utf-8")
    assert impor_csv_di(s, "stok_awal", b)["ok"]                   # bytes + BOM
    assert impor_csv_di(s, "stok_awal", csv(
        "kode;qty;tgl_kedaluwarsa;hpp_satuan\nP2;5;2027-01-01;100\n"))["ok"]
    r = impor_csv_di(s, "stok_awal", "tidak_ada.csv")
    assert not r["ok"] and "tidak ditemukan" in r["pesan"]
    assert not impor_csv_di(s, "stok_awal", None)["ok"]
