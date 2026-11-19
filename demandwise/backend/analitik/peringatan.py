"""Orkestrasi peringatan dini: notifikasi stok, batch, musim; sinkron rekomendasi; tunda_pesan."""
import pandas as pd

from . import _db, _integrasi, kedaluwarsa, musiman
from ._util import hari_ini, tgl_id
from .stok import hitung_stok_status

_JENIS_BATCH = {"waspada": "batch_waspada", "siaga": "batch_siaga", "kritis": "batch_kritis"}
_LEVEL_NOTIF = {"waspada": "waspada", "siaga": "siaga", "kritis": "kritis"}


def kirim_notif_stok(h) -> int:
    n = 0
    for r in hitung_stok_status(h).itertuples():
        if r.status == "menipis":
            ok = _integrasi.kirim(
                "stok_menipis", "waspada", f"Stok menipis: {r.nama_produk}",
                f"Stok {r.nama_produk} tinggal {r.stok_saat_ini}, di bawah reorder point {r.reorder_point:.0f}. "
                f"Kebutuhan selama lead time ±{r.prediksi_demand_lead_time:.0f} + safety stock {r.safety_stock}.",
                "produk", int(r.produk_id))
        elif r.status == "overstock":
            ok = _integrasi.kirim(
                "stok_overstock", "info", f"Stok berlebih: {r.nama_produk}",
                f"Stok {r.nama_produk} {r.stok_saat_ini} melebihi reorder point {r.reorder_point:.0f} "
                "ditambah kebutuhan 30 hari ke depan. Tahan pemesanan.", "produk", int(r.produk_id))
        else:
            ok = False
        n += int(ok)
    return n


def kirim_notif_batch(risiko: pd.DataFrame) -> int:
    n = 0
    for r in risiko[risiko["jenis_tindakan"].notna()].itertuples():
        sisa = f"{r.sisa_hari} hari lagi" if r.sisa_hari >= 0 else f"sudah lewat {abs(r.sisa_hari)} hari"
        ok = _integrasi.kirim(
            _JENIS_BATCH[r.level], _LEVEL_NOTIF[r.level], f"Batch {r.level}: {r.nama_produk}",
            f"Batch #{r.batch_id} {r.nama_produk} kedaluwarsa {tgl_id(r.tgl_kedaluwarsa)} ({sisa}). "
            f"Stok {r.stok_batch}, diperkirakan laku {r.proyeksi_laku:.0f}, berisiko {r.jumlah_berisiko} unit. "
            f"Saran: {r.rekomendasi}", "batch_stok", int(r.batch_id), dedupe="semua")
        n += int(ok)
    return n


def segarkan_tunda_pesan(risiko: pd.DataFrame) -> int:
    """Lepas tanda tunda_pesan pada produk yang sudah tidak punya batch berisiko."""
    masih = set(risiko.loc[risiko["jenis_tindakan"].notna(), "produk_id"]) if not risiko.empty else set()
    df = _db.baca("SELECT id, tunda_pesan FROM produk")
    on = df[df["tunda_pesan"].astype(str).str.lower().isin(["1", "true", "t"])]
    lepas = [int(i) for i in on["id"] if int(i) not in masih]
    for i in lepas:
        _db.jalankan("UPDATE produk SET tunda_pesan = :v WHERE id = :p", {"v": False, "p": i})
    return len(lepas)


def jalankan_semua(h=None) -> dict:
    h = h if h is not None else hari_ini()
    risiko = kedaluwarsa.hitung_risiko(h)
    rek = kedaluwarsa.sinkron_rekomendasi(risiko)
    out = {"stok": kirim_notif_stok(h), "batch": kirim_notif_batch(risiko),
           "musim": musiman.periksa_musim_mendekat(h), "rekomendasi": rek,
           "tunda_pesan_dilepas": segarkan_tunda_pesan(risiko)}
    out["total"] = out["stok"] + out["batch"] + out["musim"]
    return out
