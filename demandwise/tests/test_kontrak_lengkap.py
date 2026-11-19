"""
Kesesuaian backend dengan KONTRAK.md: semua fungsi bagian 2 ada di backend.api, dan DataFrame bagian 3
punya kolom yang wajib sama. Memakai SALINAN SQLite dummy (database asli tidak berubah).
"""
import datetime as dt
import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine

import backend.api as api
from backend import db as dbmod
from backend.analitik import _db as adb

ROOT = Path(__file__).resolve().parents[1]
SUMBER = ROOT / "data_dummy" / "demandwise_dummy.sqlite"

FUNGSI_KONTRAK = """login get_produk tambah_produk simpan_penjualan catat_barang_masuk catat_retur catat_barang_rusak
get_batch simpan_opname simpan_biaya catat_writeoff impor_csv kirim_notifikasi get_notifikasi tandai_dibaca
get_rekomendasi_pembelian buat_draf_pesanan setujui_pesanan revisi_pesanan get_teks_pesanan_wa simpan_jadwal_kirim
terima_pesanan get_rekomendasi_harga setujui_harga ubah_harga_manual get_laporan_laba
jalankan_prediksi get_prediksi get_stok_status get_risiko_kedaluwarsa get_rekomendasi_tindakan setujui_tindakan
tolak_tindakan get_indeks_musim get_event_musiman simpan_event get_profit_produk get_tren_produk simpan_koreksi
evaluasi_dan_retrain get_evaluasi_model get_ringkasan_dashboard""".split()

KOLOM = {
    "3.1": "produk_id nama_produk tanggal qty_aktual qty_prediksi tipe",
    "3.2": "produk_id nama_produk stok_saat_ini prediksi_demand_lead_time safety_stock reorder_point status selisih_dari_rop",
    "3.3": "batch_id produk_id nama_produk tgl_kedaluwarsa sisa_hari stok_batch prediksi_harian proyeksi_laku jumlah_berisiko level rekomendasi",
    "3.4": "produk_id nama_produk bulan indeks event_terkait",
    "3.5": "produk_id nama_produk pemasok stok_saat_ini prediksi_lead_time safety_stock pesanan_berjalan qty_hitung batas_masa_simpan qty_rekomendasi ditunda",
    "3.6": "produk_id nama_produk hpp harga_saat_ini harga_pesaing_rata2 indeks_musim harga_rekomendasi margin_persen alasan",
}
URUTAN_LABA = ["Penjualan", "HPP", "Laba Kotor", "Biaya Operasional", "Kerugian Kedaluwarsa (Write-off)", "Laba Bersih"]


@pytest.fixture(scope="module", autouse=True)
def salinan_db(tmp_path_factory):
    if not SUMBER.exists():
        pytest.skip("data_dummy/demandwise_dummy.sqlite tidak ada")
    tujuan = tmp_path_factory.mktemp("kontrak") / "uji.sqlite"
    shutil.copy(SUMBER, tujuan)
    eng = dbmod.buat_engine(f"sqlite:///{tujuan}")
    lama = (dbmod._engine, dbmod._SessionLocal)
    dbmod._engine, dbmod._SessionLocal = eng, None
    adb.set_engine(eng)
    yield
    dbmod._engine, dbmod._SessionLocal = lama
    adb.set_engine(create_engine("sqlite://"))


def test_semua_fungsi_kontrak_ada_di_api():
    assert [f for f in FUNGSI_KONTRAK if not callable(getattr(api, f, None))] == []
    assert set(FUNGSI_KONTRAK) <= set(api.__all__)


def _kol(df):
    return list(df.columns)


def test_kolom_dataframe_sesuai_kontrak():
    assert _kol(api.get_prediksi(1)) == KOLOM["3.1"].split()
    assert _kol(api.get_stok_status()) == KOLOM["3.2"].split()
    assert _kol(api.get_risiko_kedaluwarsa()) == KOLOM["3.3"].split()
    assert _kol(api.get_indeks_musim()) == KOLOM["3.4"].split()
    assert _kol(api.get_rekomendasi_pembelian()) == KOLOM["3.5"].split()
    assert _kol(api.get_rekomendasi_harga()) == KOLOM["3.6"].split()


def test_laporan_laba_urutan_dan_rumus():
    lb = api.get_laporan_laba(dt.date(2026, 10, 1), dt.date(2026, 11, 9))
    assert _kol(lb) == ["komponen", "jumlah"] and list(lb["komponen"]) == URUTAN_LABA
    j = dict(zip(lb["komponen"], lb["jumlah"]))
    assert j["Laba Kotor"] == j["Penjualan"] - j["HPP"]
    assert j["Laba Bersih"] == j["Laba Kotor"] - j["Biaya Operasional"] - j["Kerugian Kedaluwarsa (Write-off)"]


def test_format_hasil_aksi_baku():
    r = api.login("tidak_ada", "salah")
    assert set(r) == {"ok", "pesan", "data"} and r["ok"] is False


def test_sambungan_wulan_naila():
    """tunda_pesan (Wulan menulis) dibaca pembelian (Naila); prediksi pembelian = get_stok_status Wulan."""
    st = api.get_stok_status().set_index("produk_id")
    rp = api.get_rekomendasi_pembelian().set_index("produk_id")
    assert (rp["safety_stock"] == st["safety_stock"].reindex(rp.index)).mean() > 0.95
    rek = api.get_rekomendasi_tindakan()
    baru = rek[rek["status"] == "menunggu"]
    if len(baru):
        r = api.setujui_tindakan(int(baru.iloc[0]["id"]))
        assert r["ok"]
        pid = int(baru.iloc[0]["produk_id"])
        row = api.get_rekomendasi_pembelian().set_index("produk_id").loc[pid]
        assert bool(row["ditunda"]) and row["qty_rekomendasi"] == 0
