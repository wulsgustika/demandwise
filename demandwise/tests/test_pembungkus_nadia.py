"""Tes pembungkus (fungsi tanpa akhiran _di) yang membuka sesinya sendiri.
Memakai database SQLite sementara lewat penggantian engine di backend.db."""
import io
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.db as db
from backend import input_data as nd
from backend.models import Base, BatchStok, Kategori, Pemasok, Produk


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 't.sqlite'}", future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    with db.get_session() as s:
        s.add(Kategori(id=1, nama="Sembako"))
        s.add(Pemasok(id=1, nama="A", lead_time_hari=2))
        s.add(Produk(id=1, kode="P1", nama="Susu", kategori_id=1, pemasok_id=1, harga_jual=12000))
        s.add(BatchStok(id=1, produk_id=1, tgl_masuk=date(2026, 11, 1), tgl_kedaluwarsa=date(2027, 1, 1),
                        jumlah_awal=10, jumlah_sisa=10, hpp_satuan=8000, status="aktif"))
        s.commit()
    return engine


def test_semua_pembungkus_menyimpan_dan_mengembalikan_dict(app_db):
    t = date(2026, 11, 10)
    assert nd.catat_retur(1, 1, "Rusak", t)["ok"]
    assert nd.catat_barang_rusak(1, 1, 1, "Penyok", t)["ok"]
    r = nd.catat_writeoff(1, 2, t)
    assert r["ok"] and r["data"]["total_rugi"] == 16000
    assert nd.simpan_opname(t, [{"produk_id": 1, "stok_fisik": 4}])["ok"]
    assert nd.simpan_biaya(t, "Listrik", 1000, None)["ok"]
    assert nd.tambah_produk({"kode": "X", "nama": "Baru", "kategori": "Sembako", "pemasok": "A",
                             "satuan": "pcs", "harga_jual": 100})["ok"]
    assert nd.get_batch().iloc[0]["jumlah_sisa"] == 4
    assert len(nd.get_produk()) == 2
    assert len(nd.get_notifikasi(belum_dibaca=True)) == 1


def test_pembungkus_gagal_tidak_menyimpan_dan_tidak_error(app_db):
    r = nd.catat_retur(1, 999, "k", date(2026, 11, 10))
    assert r["ok"] is False and r["data"] is None and "tidak cukup" in r["pesan"]
    assert nd.get_batch().iloc[0]["jumlah_sisa"] == 10


def test_impor_csv_pembungkus_commit_dan_rollback(app_db):
    ok = nd.impor_csv("penjualan", io.StringIO("tanggal,kode,qty\n2026-11-10,P1,3\n"))
    assert ok["ok"] and nd.get_batch().iloc[0]["jumlah_sisa"] == 7
    gagal = nd.impor_csv("penjualan", io.StringIO("tanggal,kode,qty\n2026-11-10,P1,2\n2026-11-10,P1,50\n"))
    assert not gagal["ok"] and nd.get_batch().iloc[0]["jumlah_sisa"] == 7   # tidak ada yang tersimpan
