"""Tes sambungan Wulan: rekomendasi pembelian memakai get_stok_status()."""
import sys
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models import (Base, BatchStok, DetailPenjualan, Pemasok, Produk,
                            TransaksiPenjualan)
from backend.pembelian import (ambil_stok_status_wulan, buat_draf_dari_rekomendasi,
                               gabung_prediksi_wulan, get_prediksi_sementara,
                               hitung_rekomendasi_pembelian)

HARI = date(2026, 11, 17)
KOLOM_STOK = ["produk_id", "nama_produk", "stok_saat_ini", "prediksi_demand_lead_time",
              "safety_stock", "reorder_point", "status", "selisih_dari_rop"]


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        sesi.add(Pemasok(id=1, nama="Pemasok A", lead_time_hari=3))
        sesi.add_all([
            Produk(id=1, kode="P1", nama="Beras", pemasok_id=1, lead_time_hari=5,
                   umur_simpan_hari=6, harga_beli_terakhir=1000),
            Produk(id=2, kode="P2", nama="Susu", pemasok_id=1, lead_time_hari=2,
                   umur_simpan_hari=100, harga_beli_terakhir=2000),
        ])
        sesi.commit()
        yield sesi


def _stok_status(*baris):
    """baris: (produk_id, prediksi_demand_lead_time, safety_stock)."""
    return pd.DataFrame(
        [{"produk_id": p, "nama_produk": "x", "stok_saat_ini": 0,
          "prediksi_demand_lead_time": d, "safety_stock": ss, "reorder_point": d + ss,
          "status": "aman", "selisih_dari_rop": 0} for p, d, ss in baris],
        columns=KOLOM_STOK)


def _jual(s, produk_id, qty):
    t = TransaksiPenjualan(tanggal=HARI - timedelta(days=5), total=0)
    s.add(t)
    s.flush()
    s.add(DetailPenjualan(transaksi_id=t.id, produk_id=produk_id, batch_id=1,
                          qty=qty, harga_satuan=1000, hpp_satuan=800))


def test_angka_wulan_menggantikan_angka_palsu(s):
    _jual(s, 1, 60)   # palsu: prediksi_lead_time 10, safety stock 2
    s.commit()
    st = _stok_status((1, 25.0, 4), (2, 6.0, 1))
    r = hitung_rekomendasi_pembelian(s, HARI, st).set_index("produk_id").loc[1]
    assert r["prediksi_lead_time"] == pytest.approx(25.0)
    assert r["safety_stock"] == pytest.approx(4.0)
    assert r["qty_hitung"] == 29            # 25 + 4 - 0 - 0


def test_prediksi_harian_diturunkan_dari_lead_time_wulan(s):
    palsu = get_prediksi_sementara(s, HARI)
    hasil = gabung_prediksi_wulan(s, palsu, _stok_status((1, 25.0, 4)))
    assert hasil[1]["prediksi_harian"] == pytest.approx(5.0)   # 25 / lead time 5


def test_batas_masa_simpan_memakai_prediksi_harian_wulan(s):
    st = _stok_status((1, 25.0, 4))
    r = hitung_rekomendasi_pembelian(s, HARI, st).set_index("produk_id").loc[1]
    # harian 5 x sisa umur (umur 6 - lead time 5 = 1) = 5
    assert r["batas_masa_simpan"] == 5
    assert r["qty_rekomendasi"] == 5        # dibatasi masa simpan (29 > 5)


def test_produk_tidak_ada_di_data_wulan_tetap_palsu(s):
    _jual(s, 2, 30)   # palsu: harian 1, lead time 2 -> prediksi_lead_time 2
    s.commit()
    st = _stok_status((1, 25.0, 4))          # produk 2 tidak ada
    df = hitung_rekomendasi_pembelian(s, HARI, st).set_index("produk_id")
    assert df.loc[1, "prediksi_lead_time"] == pytest.approx(25.0)
    assert df.loc[2, "prediksi_lead_time"] == pytest.approx(2.0)


def test_angka_kosong_dari_wulan_memakai_palsu(s):
    _jual(s, 1, 60)
    s.commit()
    st = _stok_status((1, float("nan"), 4))
    r = hitung_rekomendasi_pembelian(s, HARI, st).set_index("produk_id").loc[1]
    assert r["prediksi_lead_time"] == pytest.approx(10.0)
    assert r["safety_stock"] == pytest.approx(2.0)


def test_tanpa_data_wulan_perilaku_lama_tetap(s):
    _jual(s, 1, 60)
    s.commit()
    r = hitung_rekomendasi_pembelian(s, HARI).set_index("produk_id").loc[1]
    assert r["prediksi_lead_time"] == pytest.approx(10.0)
    assert r["safety_stock"] == pytest.approx(2.0)


def test_produk_wulan_yang_tidak_aktif_di_kita_diabaikan(s):
    hasil = gabung_prediksi_wulan(s, get_prediksi_sementara(s, HARI),
                                  _stok_status((99, 50.0, 5)))
    assert 99 not in hasil


def test_draf_pesanan_memakai_angka_wulan(s):
    st = _stok_status((1, 25.0, 4), (2, 40.0, 6))
    h = buat_draf_dari_rekomendasi(s, HARI, st)
    s.commit()
    assert len(h["pesanan_id"]) == 1        # satu pesanan untuk Pemasok A
    from backend.models import DetailPesanan
    qty = {d.produk_id: d.qty_final for d in s.query(DetailPesanan).all()}
    assert qty == {1: 5, 2: 46}             # Beras dibatasi masa simpan, Susu 40 + 6


def test_ambil_stok_status_wulan_aman_tanpa_modul(monkeypatch):
    # Modul backend.analitik tidak bisa dimuat -> None, bukan error.
    monkeypatch.setitem(sys.modules, "backend.analitik", None)
    assert ambil_stok_status_wulan() is None


def test_ambil_stok_status_wulan_aman_kalau_wulan_error(monkeypatch):
    import types
    palsu = types.ModuleType("backend.analitik")

    def rusak():
        raise RuntimeError("database Wulan tidak terhubung")

    palsu.get_stok_status = rusak
    monkeypatch.setitem(sys.modules, "backend.analitik", palsu)
    assert ambil_stok_status_wulan() is None


def test_ambil_stok_status_wulan_hasil_kosong_dianggap_tidak_ada(monkeypatch):
    import types
    palsu = types.ModuleType("backend.analitik")
    palsu.get_stok_status = lambda: pd.DataFrame(columns=KOLOM_STOK)
    monkeypatch.setitem(sys.modules, "backend.analitik", palsu)
    assert ambil_stok_status_wulan() is None
