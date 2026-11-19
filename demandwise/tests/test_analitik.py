"""
Uji otomatis modul analitik (Wulan). Jalankan dari akar proyek:   pytest tests -q
Memakai SALINAN SQLite dummy, jadi database asli tidak berubah.
"""
import math
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import konfig  # noqa: E402
from backend.analitik import (_db, evaluasi_dan_retrain, get_event_musiman, get_evaluasi_model,  # noqa: E402
                              get_indeks_musim, get_prediksi, get_profit_produk,
                              get_rekomendasi_tindakan, get_ringkasan_dashboard,
                              get_risiko_kedaluwarsa, get_stok_status, get_tren_produk,
                              setujui_tindakan, simpan_event, simpan_koreksi, tolak_tindakan)
from backend.analitik import kedaluwarsa, k, musiman  # noqa: E402

konfig.RAISE_ERROR = True


@pytest.fixture(scope="module", autouse=True)
def db(tmp_path_factory):
    salin = tmp_path_factory.mktemp("db") / "uji.sqlite"
    shutil.copy(ROOT / "data_dummy" / "demandwise_dummy.sqlite", salin)
    _db.set_engine(create_engine(f"sqlite:///{salin}"))
    yield
    _db._engine = None


def test_format_aksi_baku():
    for r in [simpan_event("Uji", "2026-12-01", "2026-12-05"), simpan_event("", "2026-12-01", "2026-12-05"),
              simpan_koreksi(1, "2026-12-01", 3, "x"), setujui_tindakan(99999), tolak_tindakan(99999)]:
        assert set(r) == {"ok", "pesan", "data"} and isinstance(r["ok"], bool)


def test_kolom_kontrak():
    assert list(get_prediksi(1, 30).columns) == ["produk_id", "nama_produk", "tanggal", "qty_aktual", "qty_prediksi", "tipe"]
    assert list(get_stok_status().columns) == ["produk_id", "nama_produk", "stok_saat_ini", "prediksi_demand_lead_time",
                                               "safety_stock", "reorder_point", "status", "selisih_dari_rop"]
    assert list(get_risiko_kedaluwarsa().columns) == ["batch_id", "produk_id", "nama_produk", "tgl_kedaluwarsa", "sisa_hari",
                                                      "stok_batch", "prediksi_harian", "proyeksi_laku", "jumlah_berisiko",
                                                      "level", "rekomendasi"]
    assert list(get_indeks_musim().columns) == ["produk_id", "nama_produk", "bulan", "indeks", "event_terkait"]
    assert {"kuadran", "margin_persen", "laba_bersih"} <= set(get_profit_produk().columns)
    assert {"kecepatan", "arah"} <= set(get_tren_produk().columns)


def test_prediksi_tipe_dan_tidak_negatif():
    p = get_prediksi(8, 30)
    assert set(p["tipe"]) == {"historis", "prediksi"}
    dep = p[p["tipe"] == "prediksi"]
    assert len(dep) == 30 and (dep["qty_prediksi"] >= 0).all() and dep["qty_aktual"].isna().all()


def test_stok_status_rumus_dan_batas():
    s = get_stok_status()
    assert set(s["status"]) <= {"menipis", "aman", "overstock"}
    menipis = s[s["status"] == "menipis"]
    assert (menipis["stok_saat_ini"] <= menipis["reorder_point"] + 1e-9).all()
    # ROP = prediksi demand lead time + safety stock ; selisih = stok - ROP
    assert np.allclose(s["reorder_point"], s["prediksi_demand_lead_time"] + s["safety_stock"], atol=0.11)
    assert np.allclose(s["selisih_dari_rop"], s["stok_saat_ini"] - s["reorder_point"], atol=0.11)
    assert (s["safety_stock"] >= 0).all()


def test_risiko_rumus_kontrak():
    r = get_risiko_kedaluwarsa()
    pos = r[r["sisa_hari"] >= 0]
    esti = np.maximum(0, pos["stok_batch"] - pos["prediksi_harian"] * pos["sisa_hari"]).round()
    assert np.allclose(pos["jumlah_berisiko"], esti, atol=1)
    for x in r.itertuples():
        if x.sisa_hari <= 7: assert x.level == "kritis"
        elif x.sisa_hari <= 14: assert x.level == "siaga"
        elif x.sisa_hari <= 30: assert x.level == "waspada"
        else: assert x.level == "aman"


def test_diskon_tidak_di_bawah_hpp():
    for hpp, jual, pct in [(10000, 12000, 30), (10000, 10500, 30), (8000, 20000, 10), (9000, 9000, 30)]:
        hd = kedaluwarsa.harga_diskon(jual, pct, hpp)
        assert hd >= hpp and hd <= jual


def test_indeks_musim_definisi():
    idx = get_indeks_musim()
    assert idx["bulan"].between(1, 12).all() and (idx["indeks"] > 0).all()
    # rata-rata 12 indeks per produk mendekati 1 (rata-rata bulan / rata-rata seluruh)
    assert abs(idx.groupby("produk_id")["indeks"].mean().mean() - 1) < 0.25
    nastar = idx[idx["nama_produk"] == "Kue Nastar Toples"]
    assert nastar["indeks"].max() > 1.2


def test_event_dan_validasi():
    assert simpan_event("Pasar Murah", "2026-11-20", "2026-11-25")["ok"]
    assert not simpan_event("Pasar Murah", "2026-11-20", "2026-11-25")["ok"]          # duplikat
    assert not simpan_event("Salah", "2026-11-26", "2026-11-25")["ok"]                # terbalik
    assert not simpan_event("Salah", "bukan-tanggal", "2026-11-25")["ok"]
    ev = get_event_musiman()
    assert "Pasar Murah" in set(ev["nama"]) and (ev["sumber"] == "manual").any()


def test_koreksi_mengubah_prediksi():
    assert simpan_koreksi(8, "2026-11-12", 77, "Ada acara")["ok"]
    p = get_prediksi(8, 10)
    assert float(p.loc[p["tanggal"] == pd.Timestamp("2026-11-12"), "qty_prediksi"].iloc[0]) == 77.0
    assert not simpan_koreksi(8, "2026-11-12", -1, "x")["ok"]


def test_alur_tindakan():
    rek = get_rekomendasi_tindakan()
    assert not rek.empty and (rek["status"] == "menunggu").all()
    assert (rek["harga_diskon"].dropna() >= rek["hpp_satuan"][rek["harga_diskon"].notna()]).all()
    a, b = int(rek["id"].iloc[0]), int(rek["id"].iloc[1])
    pid = int(rek["produk_id"].iloc[0])
    r = setujui_tindakan(a)
    assert r["ok"] and not setujui_tindakan(a)["ok"]
    tunda = _db.baca("SELECT tunda_pesan FROM produk WHERE id = :i", {"i": pid})["tunda_pesan"].iloc[0]
    assert str(tunda).lower() in ("1", "true")
    assert tolak_tindakan(b, "Retur ke pemasok lain")["ok"]
    st = get_rekomendasi_tindakan().set_index("id")["status"]
    assert st[a] == "disetujui" and st[b] == "tindakan_lain"


def test_dashboard():
    d = get_ringkasan_dashboard()
    for kunci in ["tanggal_acuan", "penjualan_30_hari", "laba_bersih_30_hari", "produk_menipis", "batch_kritis",
                  "rekomendasi_menunggu", "mape_terbaru", "musim_mendekat"]:
        assert kunci in d
    assert d["total_produk_aktif"] == d["produk_menipis"] + d["produk_aman"] + d["produk_overstock"]


def test_evaluasi_dan_versi():
    ev = get_evaluasi_model()
    assert {"moving_average", "random_forest"} <= set(ev["model"]) and ev["dipakai"].any()
    assert ev["versi"].nunique() == 1


def test_laporan_laba_sendiri_rumus():
    from backend.analitik import _integrasi
    lap = _integrasi.laba_sendiri("2026-10-10", "2026-11-08").set_index("komponen")["jumlah"]
    assert math.isclose(lap["Laba Bersih"], lap["Penjualan"] - lap["HPP"] - lap["Biaya Operasional"]
                        - lap["Kerugian Kedaluwarsa (Write-off)"], rel_tol=1e-9)


def test_notifikasi_batch_untuk_semua_level():
    """KONTRAK bagian 5 + swimlane bagian 3: tiap batch waspada/siaga/kritis dapat notifikasi dan rekomendasi."""
    r = get_risiko_kedaluwarsa()
    berlevel = r[r["level"] != "aman"]
    notif = _db.baca("SELECT jenis, ref_id FROM notifikasi WHERE jenis LIKE 'batch_%'")
    assert set(notif["ref_id"].astype(int)) == set(berlevel["batch_id"].astype(int))
    for x in berlevel.itertuples():
        assert f"batch_{x.level}" in set(notif.loc[notif["ref_id"] == x.batch_id, "jenis"])
    rek = _db.baca("SELECT batch_id FROM rekomendasi_tindakan")
    assert set(berlevel["batch_id"].astype(int)) <= set(rek["batch_id"].astype(int))


def test_stok_musiman_dibatasi_masa_simpan(monkeypatch):
    monkeypatch.setenv("DEMANDWISE_HARI_INI", "2026-11-10")     # Natal mulai 10 Des = H-30
    df = musiman.hitung_stok_musiman()
    assert not df.empty and (df["indeks_musim"] > 1.2).all() and (df["sisa_hari"] <= 30).all()
    assert (df["qty_rekomendasi"] >= 0).all()
    assert (df["qty_rekomendasi"] <= df["batas_masa_simpan"]).all()
    assert (df["qty_rekomendasi"] <= df["kebutuhan_musim"]).all()
    assert (df["qty_rekomendasi"] > 0).any() and df["event"].str.startswith("Natal").any()
    monkeypatch.setenv("DEMANDWISE_HARI_INI", "2026-11-09")     # H-31: belum masuk jendela
    d2 = musiman.hitung_stok_musiman()
    assert d2.empty or not d2["event"].str.startswith("Natal").any()
