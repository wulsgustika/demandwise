"""KPI untuk halaman dashboard."""
import pandas as pd

from . import _db, _integrasi, data_akses as da, k
from ._util import dict_aman, hari_ini
from . import kedaluwarsa, profit, stok


def _kosong():
    return {}


@dict_aman(_kosong)
def get_ringkasan_dashboard() -> dict:
    """Dict KPI siap tampil. Nilai uang = rupiah bulat. Daftar kunci ada di README_WULAN.md."""
    h = hari_ini()
    akhir = h - pd.Timedelta(days=1)
    awal = akhir - pd.Timedelta(days=29)
    st = stok.hitung_stok_status(h)
    risiko = kedaluwarsa.hitung_risiko(h)
    berisiko = risiko[risiko["jenis_tindakan"].notna()]   # batch berlevel (waspada/siaga/kritis) yang punya rekomendasi
    nilai_berisiko = float((berisiko["jumlah_berisiko"] * berisiko["hpp_satuan"]).sum()) if len(berisiko) else 0.0
    # laba: pakai laporan Naila bila sudah ada (sumber tunggal rumus laba)
    laba = _integrasi.laporan_laba(awal, akhir).set_index("komponen")["jumlah"]
    kec = profit.tabel_kecepatan(h=h)
    menunggu = _db.baca("SELECT COUNT(*) AS n FROM rekomendasi_tindakan WHERE status = 'menunggu' AND "
                        + _db.saring())["n"].iloc[0]
    notif = _db.baca("SELECT COUNT(*) AS n FROM notifikasi WHERE (dibaca = :f OR dibaca IS NULL) AND "
                     + _db.saring(), {"f": False})["n"].iloc[0]
    ev = _db.baca("SELECT MAX(versi) AS v, MAX(dievaluasi_pada) AS t FROM evaluasi_model WHERE "
                  + _db.saring(), tanggal=["t"])
    from .prediksi import get_evaluasi_model
    e = get_evaluasi_model()
    mape = float(e.loc[e["dipakai"], "mape"].mean()) if len(e) and e.loc[e["dipakai"], "mape"].notna().any() else None
    events = da.events()
    dekat = events[(events["tgl_mulai"] >= h) & ((events["tgl_mulai"] - h).dt.days <= 60)]
    g = lambda nm: float(laba.get(nm, 0.0))
    return {
        "tanggal_acuan": str(h.date()), "periode_awal": str(awal.date()), "periode_akhir": str(akhir.date()),
        "penjualan_30_hari": int(round(g("Penjualan"))), "laba_kotor_30_hari": int(round(g("Laba Kotor"))),
        "writeoff_30_hari": int(round(g("Kerugian Kedaluwarsa (Write-off)"))),
        "laba_bersih_30_hari": int(round(g("Laba Bersih"))),
        "total_produk_aktif": int(len(st)),
        "produk_menipis": int((st["status"] == "menipis").sum()),
        "produk_aman": int((st["status"] == "aman").sum()),
        "produk_overstock": int((st["status"] == "overstock").sum()),
        "batch_aktif": int(len(risiko)), "batch_berisiko": int((risiko["jumlah_berisiko"] >= 1).sum()),
        "batch_perlu_tindakan": int(len(berisiko)),
        "batch_waspada": int((risiko["level"] == "waspada").sum()),
        "batch_siaga": int((risiko["level"] == "siaga").sum()),
        "batch_kritis": int((risiko["level"] == "kritis").sum()),
        "nilai_stok_berisiko": int(round(nilai_berisiko)),
        "rekomendasi_menunggu": int(menunggu), "notifikasi_belum_dibaca": int(notif),
        "produk_fast": int((kec["kecepatan"] == "fast").sum()), "produk_slow": int((kec["kecepatan"] == "slow").sum()),
        "mape_terbaru": None if mape is None else round(mape, 1),
        "versi_model": ev["v"].iloc[0] if len(ev) and ev["v"].iloc[0] else None,
        "model_dilatih_pada": None if ev["t"].isna().all() else str(pd.Timestamp(ev["t"].iloc[0])),
        "musim_mendekat": [{"nama": r.nama, "tgl_mulai": str(r.tgl_mulai.date()),
                            "sisa_hari": int((r.tgl_mulai - h).days)} for r in dekat.itertuples()],
    }
