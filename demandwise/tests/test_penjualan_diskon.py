"""Tes sambungan Wulan: simpan_penjualan memakai harga diskon yang sudah disetujui."""
from datetime import date, datetime

import pytest
from sqlalchemy import select

from backend import db
from backend.models import (Base, BatchStok, DetailPenjualan, Produk,
                            RekomendasiTindakan)
from backend.penjualan import ambil_harga_diskon, simpan_penjualan


def _batch(produk_id, kedaluwarsa, sisa, hpp):
    return BatchStok(produk_id=produk_id, tgl_masuk=date(2026, 11, 1),
                     tgl_kedaluwarsa=kedaluwarsa, jumlah_awal=sisa,
                     jumlah_sisa=sisa, hpp_satuan=hpp, status="aktif")


@pytest.fixture
def sesi(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDWISE_DB_URL", f"sqlite:///{tmp_path / 'tes.sqlite'}")
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_SessionLocal", None)
    Base.metadata.create_all(db.get_engine())
    with db.get_session() as s:
        s.add(Produk(kode="P1", nama="Susu UHT", harga_jual=5000))
        s.commit()
        s.add_all([
            _batch(1, date(2026, 12, 20), 6, 3000),   # batch 1 (A)
            _batch(1, date(2027, 1, 5), 20, 3200),    # batch 2 (B)
        ])
        s.commit()
        yield s


def _rekom(s, batch_id, harga, status="disetujui", jenis="diskon", jam=10):
    s.add(RekomendasiTindakan(batch_id=batch_id, jenis=jenis, harga_diskon=harga,
                              status=status, dibuat_pada=datetime(2026, 11, 18, jam, 0)))
    s.commit()


def _detail(s):
    s.expire_all()
    d = s.execute(select(DetailPenjualan).order_by(DetailPenjualan.id)).scalars().all()
    return [(x.batch_id, x.qty, x.harga_satuan, x.hpp_satuan) for x in d]


def test_batch_diskon_dijual_harga_diskon_batch_lain_normal(sesi):
    _rekom(sesi, 1, 4000)
    r = simpan_penjualan("2026-11-18", [{"produk_id": 1, "qty": 10}])
    assert r["ok"] is True
    # 6 dari batch 1 (diskon 4000), 4 dari batch 2 (normal 5000)
    assert _detail(sesi) == [(1, 6, 4000, 3000), (2, 4, 5000, 3200)]
    assert r["data"]["total"] == 6 * 4000 + 4 * 5000


def test_rincian_memuat_harga_per_batch(sesi):
    _rekom(sesi, 1, 4000)
    r = simpan_penjualan("2026-11-18", [{"produk_id": 1, "qty": 10}])
    batch = r["data"]["rincian"][0]["batch"]
    assert [(b["batch_id"], b["harga_satuan"]) for b in batch] == [(1, 4000), (2, 5000)]
    assert r["data"]["rincian"][0]["harga_satuan"] == 5000   # harga normal produk


@pytest.mark.parametrize("status", ["menunggu", "ditolak", "tindakan_lain"])
def test_diskon_belum_disetujui_diabaikan(sesi, status):
    _rekom(sesi, 1, 4000, status=status)
    simpan_penjualan("2026-11-18", [{"produk_id": 1, "qty": 2}])
    assert _detail(sesi) == [(1, 2, 5000, 3000)]


@pytest.mark.parametrize("jenis", ["bundling", "retur_pemasok", "lainnya"])
def test_jenis_bukan_diskon_diabaikan(sesi, jenis):
    _rekom(sesi, 1, 4000, jenis=jenis)
    simpan_penjualan("2026-11-18", [{"produk_id": 1, "qty": 2}])
    assert _detail(sesi) == [(1, 2, 5000, 3000)]


@pytest.mark.parametrize("harga", [None, 0, -100])
def test_harga_diskon_kosong_atau_tidak_valid_diabaikan(sesi, harga):
    _rekom(sesi, 1, harga)
    simpan_penjualan("2026-11-18", [{"produk_id": 1, "qty": 2}])
    assert _detail(sesi) == [(1, 2, 5000, 3000)]


def test_dua_persetujuan_yang_terbaru_dipakai(sesi):
    _rekom(sesi, 1, 4500, jam=9)
    _rekom(sesi, 1, 3800, jam=11)
    simpan_penjualan("2026-11-18", [{"produk_id": 1, "qty": 2}])
    assert _detail(sesi) == [(1, 2, 3800, 3000)]


def test_diskon_lebih_mahal_dari_harga_normal_tidak_dipakai(sesi):
    _rekom(sesi, 1, 7000)
    simpan_penjualan("2026-11-18", [{"produk_id": 1, "qty": 2}])
    assert _detail(sesi) == [(1, 2, 5000, 3000)]


def test_diskon_batch_yang_tidak_terjual_tidak_berpengaruh(sesi):
    _rekom(sesi, 2, 4000)          # batch B, belum tersentuh
    simpan_penjualan("2026-11-18", [{"produk_id": 1, "qty": 2}])
    assert _detail(sesi) == [(1, 2, 5000, 3000)]


def test_tanpa_diskon_perilaku_lama_tetap(sesi):
    r = simpan_penjualan("2026-11-18", [{"produk_id": 1, "qty": 10}])
    assert r["data"]["total"] == 10 * 5000
    assert _detail(sesi) == [(1, 6, 5000, 3000), (2, 4, 5000, 3200)]


def test_ambil_harga_diskon_langsung(sesi):
    _rekom(sesi, 1, 4000)
    assert ambil_harga_diskon(sesi, [1, 2]) == {1: 4000}
    assert ambil_harga_diskon(sesi, []) == {}
