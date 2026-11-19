"""
Skenario multi-pengguna (akun baru kosong, data per user_id, data demo tetap utuh).

Memakai SALINAN demandwise.sqlite (database presentasi), jadi file asli tidak berubah.
Skenario:
  1. Pengguna A daftar -> akun tersimpan, semua data operasional kosong.
  2. A mengisi produk -> tersimpan dengan user_id A.
  3. B daftar -> tidak melihat (dan tidak bisa mengubah) data A maupun data demo.
  4. A login kembali -> datanya masih ada.
  5. Data dummy presentasi tidak berubah sedikit pun dan fitur demo tetap berjalan.
"""
import os
import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from backend import auth, db
from backend.analitik import _db as _db_analitik
from backend.api import (catat_barang_masuk, daftar_akun, get_batch, get_event_musiman, get_indeks_musim,
                         get_laporan_laba, get_notifikasi, get_prediksi, get_produk, get_profit_produk,
                         get_rekomendasi_harga, get_rekomendasi_pembelian, get_rekomendasi_tindakan,
                         get_ringkasan_dashboard, get_risiko_kedaluwarsa, get_stok_status, jalankan_prediksi,
                         login, setujui_tindakan, simpan_biaya, simpan_event, simpan_penjualan, tambah_produk,
                         tandai_dibaca)
from backend.konteks import RUANG_TERKUNCI, pakai_pengguna, pakai_ruang
from backend.models import TABEL_MILIK_PENGGUNA
from scripts.cek_data_demo import sidik_semua

ROOT = Path(__file__).resolve().parents[1]
HARI_INI = date.today()


@pytest.fixture(scope="module", autouse=True)
def database(tmp_path_factory):
    # Opsional: DW_UJI_DB_URL = database UJI (mis. branch Neon salinan). JANGAN arahkan ke database utama,
    # karena tes ini membuat akun pengguna_a / pengguna_b. Tanpa variabel ini dipakai salinan SQLite.
    url = os.environ.get("DW_UJI_DB_URL")
    if not url:
        salin = tmp_path_factory.mktemp("multi") / "demo.sqlite"
        shutil.copy(ROOT / "demandwise.sqlite", salin)
        url = f"sqlite:///{salin}"
    mp = pytest.MonkeyPatch()
    mp.setenv("DEMANDWISE_DB_URL", url)
    mp.setattr(db, "_engine", None)
    mp.setattr(db, "_SessionLocal", None)
    mp.setattr(auth, "_kolom_siap", False)
    mp.setattr(_db_analitik, "_engine", None)
    mp.setattr(_db_analitik, "_skema_siap", False)
    sebelum = sidik_semua(url)          # sidik data demo SEBELUM migrasi & sebelum akun baru dipakai
    db.get_engine()                     # migrasi aman berjalan di sini
    yield {"url": url, "sebelum": sebelum, "ids": {}}
    mp.undo()
    _db_analitik._engine = None


def _jumlah_baris_milik(uid: int) -> dict:
    with db.get_engine().connect() as c:
        return {t.name: c.execute(text(f"SELECT COUNT(*) FROM {t.name} WHERE user_id = :u"), {"u": uid}).scalar()
                for t in TABEL_MILIK_PENGGUNA}


def _daftar(nama, email, username):
    r = daftar_akun(nama, email, username, "rahasia123", "rahasia123")
    assert r["ok"] is True, r
    return r["data"]["user_id"]


# --------------------------------------------------------------------------- 1
def test_skenario1_akun_baru_tersimpan_dan_kosong(database):
    a = _daftar("Toko Pengguna A", "a@contoh.com", "pengguna_a")
    database["ids"]["A"] = a
    with db.get_engine().connect() as c:
        u = c.execute(text("SELECT username, email, akun_demo FROM users WHERE id = :i"), {"i": a}).one()
    assert u[0] == "pengguna_a" and u[1] == "a@contoh.com" and not u[2]
    r = login("pengguna_a", "rahasia123")
    assert r["ok"] and r["data"]["mode_data"] == "pengguna" and r["data"]["user_id"] == a

    with pakai_pengguna(a):
        assert get_produk(aktif_saja=False).empty
        assert get_batch(aktif_saja=False).empty
        assert get_notifikasi().empty
        assert get_stok_status().empty
        assert get_risiko_kedaluwarsa().empty
        assert get_rekomendasi_tindakan().empty
        assert get_rekomendasi_pembelian().empty
        assert get_rekomendasi_harga().empty
        assert get_event_musiman().empty
        assert get_indeks_musim().empty
        assert get_prediksi(None).empty
        assert get_profit_produk().empty
        laba = get_laporan_laba(HARI_INI - timedelta(days=365), HARI_INI)
        assert (laba["jumlah"] == 0).all()
        d = get_ringkasan_dashboard()
        assert d == {} or (d.get("penjualan_30_hari", 0) == 0 and d.get("total_produk_aktif", 0) == 0)
    # Membuka semua halaman tidak boleh membuat data apa pun untuk akun baru (tanpa data dummy otomatis).
    assert sum(_jumlah_baris_milik(a).values()) == 0


# --------------------------------------------------------------------------- 2
def test_skenario2_produk_tersimpan_dengan_user_id_a(database):
    a = database["ids"]["A"]
    with pakai_pengguna(a):
        # Kode & kategori SAMA dengan data demo -> boleh, karena unik per pemilik data.
        r = tambah_produk({"kode": "PRD-001", "nama": "Kopi Bubuk A", "kategori": "Minuman",
                           "pemasok": "CV Sumber A", "satuan": "pcs", "harga_jual": 15000,
                           "harga_beli_terakhir": 11000, "umur_simpan_hari": 180, "lead_time_hari": 2})
        assert r["ok"], r
        pid = r["data"]["produk_id"]
        database["ids"]["produk_A"] = pid
        assert catat_barang_masuk(pid, 50, HARI_INI + timedelta(days=170), 11000, HARI_INI)["ok"]
        assert simpan_penjualan(HARI_INI, [{"produk_id": pid, "qty": 5}])["ok"]
        assert simpan_biaya(HARI_INI, "Listrik", 200000, "Token listrik")["ok"]
        assert simpan_event("Promo Toko A", HARI_INI, HARI_INI + timedelta(days=3))["ok"]
        jalankan_prediksi(30)          # analitik milik A (data sedikit; boleh berhasil/gagal dengan rapi)
        df = get_produk(aktif_saja=False)
        assert list(df["kode"]) == ["PRD-001"] and list(df["nama_produk"]) == ["Kopi Bubuk A"]
        assert int(get_stok_status()["stok_saat_ini"].sum()) == 45

    milik = _jumlah_baris_milik(a)
    for tabel in ("produk", "kategori", "pemasok", "batch_stok", "transaksi_penjualan", "detail_penjualan",
                  "mutasi_stok", "biaya_operasional", "harga_jual", "event_musiman"):
        assert milik[tabel] >= 1, tabel
    with db.get_engine().connect() as c:
        assert c.execute(text("SELECT user_id FROM produk WHERE id = :p"), {"p": pid}).scalar() == a


# --------------------------------------------------------------------------- 3
def test_skenario3_pengguna_b_tidak_melihat_data_a(database):
    a, pid_a = database["ids"]["A"], database["ids"]["produk_A"]
    b = _daftar("Toko Pengguna B", "b@contoh.com", "pengguna_b")
    database["ids"]["B"] = b
    with pakai_pengguna(b):
        assert get_produk(aktif_saja=False).empty
        assert get_batch(aktif_saja=False).empty
        assert get_event_musiman().empty
        assert get_notifikasi().empty and get_stok_status().empty and get_prediksi(None).empty
        laba = get_laporan_laba(HARI_INI - timedelta(days=30), HARI_INI)
        assert (laba["jumlah"] == 0).all()
        # Tidak bisa memakai/mengubah data A atau data demo walau tahu id-nya.
        assert not catat_barang_masuk(pid_a, 10, HARI_INI + timedelta(days=30), 1000, HARI_INI)["ok"]
        assert not simpan_penjualan(HARI_INI, [{"produk_id": pid_a, "qty": 1}])["ok"]
        assert not simpan_penjualan(HARI_INI, [{"produk_id": 1, "qty": 1}])["ok"]      # produk demo
        assert not tandai_dibaca(1)["ok"]                                               # notifikasi demo
        assert not setujui_tindakan(1)["ok"]                                            # rekomendasi demo
        # B boleh memakai kode yang sama dengan A.
        assert tambah_produk({"kode": "PRD-001", "nama": "Teh B", "kategori": "Minuman", "pemasok": "UD B",
                              "satuan": "pcs", "harga_jual": 5000})["ok"]
        assert list(get_produk(aktif_saja=False)["nama_produk"]) == ["Teh B"]
    with pakai_pengguna(a):
        assert list(get_produk(aktif_saja=False)["nama_produk"]) == ["Kopi Bubuk A"]
    assert _jumlah_baris_milik(b)["produk"] == 1


def test_belum_login_tidak_bisa_baca_atau_tulis(database):
    with pakai_ruang(RUANG_TERKUNCI):
        assert get_produk(aktif_saja=False).empty
        assert not tambah_produk({"kode": "X1", "nama": "X", "kategori": "Minuman", "pemasok": "Y",
                                  "satuan": "pcs", "harga_jual": 1})["ok"]


# --------------------------------------------------------------------------- 4
def test_skenario4_a_login_kembali_data_masih_ada(database):
    a = database["ids"]["A"]
    r = login("a@contoh.com", "rahasia123")        # login ulang memakai email
    assert r["ok"] and r["data"]["user_id"] == a
    db._SessionLocal = None                         # sesi baru, seperti membuka aplikasi lagi
    with pakai_pengguna(r["data"]["user_id"]):
        df = get_produk(aktif_saja=False)
        assert list(df["nama_produk"]) == ["Kopi Bubuk A"]
        notif = get_notifikasi()
        if len(notif):   # notifikasi yang terlihat A hanyalah milik A (bukan 32 notifikasi demo)
            with db.get_engine().connect() as c:
                pemilik = {row[0] for row in c.execute(text(
                    f"SELECT DISTINCT user_id FROM notifikasi WHERE id IN ({','.join(map(str, notif['notif_id']))})"))}
            assert pemilik == {a}
        laba = get_laporan_laba(HARI_INI, HARI_INI).set_index("komponen")["jumlah"]
        assert laba["Penjualan"] == 5 * 15000 and laba["Biaya Operasional"] == 200000


# --------------------------------------------------------------------------- 5
def test_skenario5_data_demo_utuh_dan_fitur_demo_jalan(database):
    # (a) Isi data demo sama persis dengan sebelum migrasi & sebelum A/B memakai aplikasi.
    sesudah = sidik_semua(database["url"])
    beda = [t for t in database["sebelum"] if database["sebelum"][t] != sesudah[t]]
    assert beda == [], f"data demo berubah di: {beda}"

    # (b) Akun demo tetap masuk ke mode demo dan melihat data presentasi yang sama.
    r = login("pemilik", "demo123")
    assert r["ok"] and r["data"]["mode_data"] == "demo"
    with pakai_pengguna(r["data"]["user_id"]):
        produk = get_produk(aktif_saja=False)
        assert len(produk) == database["sebelum"]["produk"]["baris"]
        assert "Kopi Bubuk A" not in set(produk["nama_produk"]) and "Teh B" not in set(produk["nama_produk"])
        assert len(get_batch()) > 0 and len(get_stok_status()) > 0 and len(get_notifikasi()) > 0
        d = get_ringkasan_dashboard()
        assert d["penjualan_30_hari"] > 0 and d["total_produk_aktif"] > 0
        assert not get_prediksi(1).empty and not get_indeks_musim().empty
        laba = get_laporan_laba(date(2026, 10, 1), date(2026, 10, 31)).set_index("komponen")["jumlah"]
        assert laba["Penjualan"] > 0
