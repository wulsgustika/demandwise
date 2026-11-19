"""Tes langkah 3: simpan_penjualan. Memakai SQLite sementara."""
from datetime import date

import pytest
from sqlalchemy import func, select

from backend import db
from backend.models import (
    Base, BatchStok, DetailPenjualan, MutasiStok, Produk, TransaksiPenjualan,
)
from backend.penjualan import simpan_penjualan


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
        s.add_all([
            Produk(kode="P1", nama="Susu UHT", harga_jual=5000),
            Produk(kode="P2", nama="Teh Kotak", harga_jual=4000),
            Produk(kode="P3", nama="Tanpa Harga", harga_jual=None),
        ])
        s.commit()
        s.add_all([
            _batch(1, date(2026, 12, 20), 6, 3000),    # A
            _batch(1, date(2027, 1, 5), 20, 3200),     # B
            _batch(1, date(2027, 2, 1), 50, 3300),     # C
            _batch(2, date(2027, 1, 1), 10, 2500),
            _batch(3, date(2027, 1, 1), 10, 100),
        ])
        s.commit()
        yield s


def _hitung(s, model):
    return s.execute(select(func.count()).select_from(model)).scalar()


def _sisa(s):
    return [b.jumlah_sisa for b in s.execute(select(BatchStok).order_by(BatchStok.id)).scalars()]


def test_terpecah_ke_dua_batch(sesi):
    r = simpan_penjualan("2026-11-10", [{"produk_id": 1, "qty": 10}])
    assert r["ok"] is True
    assert r["data"]["total"] == 10 * 5000

    sesi.expire_all()
    detail = sesi.execute(select(DetailPenjualan).order_by(DetailPenjualan.id)).scalars().all()
    assert [(d.batch_id, d.qty, d.hpp_satuan, d.harga_satuan) for d in detail] == [
        (1, 6, 3000, 5000), (2, 4, 3200, 5000)]   # HPP beda per batch

    batches = sesi.execute(select(BatchStok).order_by(BatchStok.id)).scalars().all()
    assert [(b.jumlah_sisa, b.status) for b in batches[:3]] == [
        (0, "habis"), (16, "aktif"), (50, "aktif")]

    mutasi = sesi.execute(select(MutasiStok)).scalars().all()
    assert sorted(m.qty for m in mutasi) == [-6, -4]
    assert all(m.jenis == "penjualan" for m in mutasi)


def test_stok_kurang_tidak_ada_yang_tersimpan(sesi):
    sebelum = _sisa(sesi)
    r = simpan_penjualan("2026-11-10", [{"produk_id": 1, "qty": 999}])
    assert r["ok"] is False and r["data"] is None
    assert "Susu UHT" in r["pesan"] and "kurang" in r["pesan"]
    sesi.expire_all()
    assert _sisa(sesi) == sebelum
    assert _hitung(sesi, TransaksiPenjualan) == 0
    assert _hitung(sesi, DetailPenjualan) == 0
    assert _hitung(sesi, MutasiStok) == 0


def test_item_kedua_kurang_item_pertama_ikut_batal(sesi):
    sebelum = _sisa(sesi)
    r = simpan_penjualan("2026-11-10", [{"produk_id": 1, "qty": 5},
                                        {"produk_id": 2, "qty": 999}])
    assert r["ok"] is False
    sesi.expire_all()
    assert _sisa(sesi) == sebelum          # susu (item pertama) tidak berkurang
    assert _hitung(sesi, TransaksiPenjualan) == 0


def test_produk_sama_dua_baris_dijumlahkan(sesi):
    r = simpan_penjualan(date(2026, 11, 10), [{"produk_id": 1, "qty": 4},
                                              {"produk_id": 1, "qty": 4}])
    assert r["ok"] is True
    assert r["data"]["rincian"][0]["qty"] == 8
    sesi.expire_all()
    # 8 = 6 dari batch A (habis) + 2 dari batch B
    assert _sisa(sesi)[0] == 0
    assert _sisa(sesi)[1] == 18


def test_beberapa_produk_satu_transaksi(sesi):
    r = simpan_penjualan("2026-11-10", [{"produk_id": 1, "qty": 2},
                                        {"produk_id": 2, "qty": 3}])
    assert r["ok"] is True
    assert r["data"]["total"] == 2 * 5000 + 3 * 4000
    assert _hitung(sesi, TransaksiPenjualan) == 1


@pytest.mark.parametrize("tanggal,items", [
    ("2026-11-10", []),
    ("2026-11-10", [{"produk_id": 1, "qty": 0}]),
    ("2026-11-10", [{"produk_id": 1, "qty": -2}]),
    ("2026-11-10", [{"produk_id": 1}]),
    ("2026-11-10", "bukan list"),
    ("10-11-2026", [{"produk_id": 1, "qty": 1}]),
    ("2026-11-10", [{"produk_id": 99, "qty": 1}]),        # produk tidak ada
    ("2026-11-10", [{"produk_id": 3, "qty": 1}]),         # harga jual belum diatur
])
def test_input_tidak_valid_ditolak_tanpa_crash(sesi, tanggal, items):
    r = simpan_penjualan(tanggal, items)
    assert r["ok"] is False and r["data"] is None and r["pesan"]
    assert _hitung(sesi, TransaksiPenjualan) == 0
