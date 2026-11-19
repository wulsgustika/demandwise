import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.harga import (KOLOM_HARGA, get_harga_pesaing_rata2, get_hpp_per_produk,
                           get_rekomendasi_harga, hitung_rekomendasi_harga)
from backend.models import Base, BatchStok, HargaPesaing, IndeksMusim, Produk

HARI_INI = date(2026, 11, 18)


@pytest.fixture
def s():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as sesi:
        # 1: lengkap (HPP, harga jual, pesaing, musim)
        sesi.add(Produk(id=1, kode="P1", nama="Beras", harga_beli_terakhir=7500, harga_jual=9000))
        # 2: tanpa harga_beli_terakhir, HPP dari batch aktif terbaru
        sesi.add(Produk(id=2, kode="P2", nama="Gula", harga_beli_terakhir=None, harga_jual=15000))
        # 3: tanpa HPP sama sekali
        sesi.add(Produk(id=3, kode="P3", nama="Minyak", harga_beli_terakhir=None, harga_jual=None))
        # 4: tidak aktif
        sesi.add(Produk(id=4, kode="P4", nama="Teh", harga_beli_terakhir=5000, aktif=False))
        sesi.flush()
        sesi.add_all([
            BatchStok(produk_id=2, tgl_masuk=date(2026, 10, 1), tgl_kedaluwarsa=date(2027, 1, 1),
                      jumlah_awal=10, jumlah_sisa=10, hpp_satuan=11000),
            BatchStok(produk_id=2, tgl_masuk=date(2026, 11, 1), tgl_kedaluwarsa=date(2027, 2, 1),
                      jumlah_awal=10, jumlah_sisa=10, hpp_satuan=12000),
            # batch habis tidak boleh dipakai sebagai cadangan HPP
            BatchStok(produk_id=3, tgl_masuk=date(2026, 11, 10), tgl_kedaluwarsa=date(2027, 2, 1),
                      jumlah_awal=10, jumlah_sisa=0, hpp_satuan=999, status="habis"),
        ])
        # pesaing: A harga lama 5.000 lalu 9.000 (yang dipakai 9.000), B 10.000
        sesi.add_all([
            HargaPesaing(produk_id=1, nama_pesaing="A", harga=5000, tanggal=date(2026, 1, 1)),
            HargaPesaing(produk_id=1, nama_pesaing="A", harga=9000, tanggal=date(2026, 11, 1)),
            HargaPesaing(produk_id=1, nama_pesaing="B", harga=10000, tanggal=date(2026, 11, 2)),
            # tanggal di masa depan tidak ikut
            HargaPesaing(produk_id=1, nama_pesaing="C", harga=1, tanggal=date(2027, 1, 1)),
        ])
        sesi.add_all([IndeksMusim(produk_id=1, bulan=11, indeks=1.4),
                      IndeksMusim(produk_id=1, bulan=12, indeks=0.5)])
        sesi.commit()
        yield sesi


def _baris(df, pid):
    return df[df["produk_id"] == pid].iloc[0]


def test_hpp_utama_lalu_cadangan_dari_batch_aktif(s):
    hpp = get_hpp_per_produk(s)
    assert hpp[1] == 7500
    assert hpp[2] == 12000          # batch aktif terbaru
    assert 3 not in hpp             # batch 'habis' tidak dihitung


def test_pesaing_pakai_harga_terbaru_tiap_pesaing(s):
    rata = get_harga_pesaing_rata2(s, HARI_INI)
    assert rata[1] == 9500          # (9.000 + 10.000) / 2, bukan campur harga lama
    assert 2 not in rata


def test_kolom_dan_produk_tidak_aktif_tidak_muncul(s):
    df = hitung_rekomendasi_harga(s, HARI_INI)
    assert list(df.columns) == KOLOM_HARGA
    assert set(df["produk_id"]) == {1, 2, 3}


def test_produk_lengkap_memakai_musim_dan_pesaing(s):
    r = _baris(hitung_rekomendasi_harga(s, HARI_INI), 1)
    assert r["hpp"] == 7500
    assert r["harga_saat_ini"] == 9000
    assert r["harga_pesaing_rata2"] == 9500
    assert r["indeks_musim"] == 1.4         # bulan November
    assert r["harga_rekomendasi"] >= 7500 / 0.85
    assert r["margin_persen"] >= 15
    assert "indeks musim" in r["alasan"]


def test_bulan_lain_memakai_indeks_bulan_itu(s):
    r = _baris(hitung_rekomendasi_harga(s, date(2026, 12, 15)), 1)
    assert r["indeks_musim"] == 0.5


def test_indeks_musim_kosong_dianggap_netral_dan_dicatat(s):
    r = _baris(hitung_rekomendasi_harga(s, HARI_INI), 2)
    assert r["indeks_musim"] == 1.0
    assert "belum ada" in r["alasan"]
    assert r["harga_rekomendasi"] == 16000   # 12.000 / 0,75 = 16.000


def test_produk_tanpa_pesaing_pesaing_kosong(s):
    r = _baris(hitung_rekomendasi_harga(s, HARI_INI), 2)
    assert pd_isna(r["harga_pesaing_rata2"])


def test_produk_tanpa_hpp_tetap_muncul_tanpa_harga(s):
    r = _baris(hitung_rekomendasi_harga(s, HARI_INI), 3)
    assert pd_isna(r["harga_rekomendasi"]) and pd_isna(r["margin_persen"])
    assert "HPP belum ada" in r["alasan"]


def test_margin_semua_baris_minimal_15_persen(s):
    df = hitung_rekomendasi_harga(s, HARI_INI).dropna(subset=["harga_rekomendasi"])
    assert (df["margin_persen"] >= 15).all()


def test_error_database_mengembalikan_tabel_kosong(monkeypatch):
    import backend.db as db

    def rusak():
        raise RuntimeError("database mati")
    monkeypatch.setattr(db, "get_session", rusak)
    df = get_rekomendasi_harga()
    assert df.empty and list(df.columns) == KOLOM_HARGA


def pd_isna(x):
    import pandas as pd
    return bool(pd.isna(x))
