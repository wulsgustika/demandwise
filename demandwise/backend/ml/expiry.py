"""Risiko kedaluwarsa & mesin rekomendasi tindakan (mock aturan bisnis sesuai spesifikasi)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import mock_data as md
from .. import stok_service
from ..notifikasi_service import kirim_notifikasi
from ..state import store, now
from . import prediksi

LEVELS = ["Kritis", "Siaga", "Waspada", "Normal"]


def level_dari_hari(sisa: int) -> str:
    return "Kritis" if sisa <= 7 else "Siaga" if sisa <= 14 else "Waspada" if sisa <= 30 else "Normal"


def get_risiko_kedaluwarsa() -> pd.DataFrame:
    """-> DataFrame[batch_id, nama, kategori, rak, qty, tgl_exp, sisa_hari, proyeksi_laku, berisiko, nilai_risiko, level, rekomendasi, keputusan]
    berisiko = stok batch - prediksi harian x sisa hari (FEFO: batch lebih awal terjual lebih dulu)."""
    b = stok_service.get_batch()
    pred = prediksi.get_prediksi(None, prediksi.HORIZON_MAX)
    cum = {pid: g.sort_values("tanggal").yhat.cumsum().values for pid, g in pred.groupby("produk_id")}
    avg = pred.groupby("produk_id").yhat.mean()
    rows = []
    for pid, g in b.groupby("produk_id"):
        g = g.sort_values("tgl_exp")
        kum_qty = 0
        for r in g.itertuples():
            kum_qty += r.qty
            h = max(int(r.sisa_hari), 0)
            c = cum[pid]
            demand = float(c[min(h, len(c)) - 1]) if h > 0 else 0.0
            if h > len(c):
                demand += (h - len(c)) * float(avg[pid])
            ber = int(np.clip(round(kum_qty - demand), 0, r.qty))
            rows.append(dict(batch_id=r.batch_id, produk_id=pid, nama=r.nama, kategori=r.kategori, rak=r.rak, qty=int(r.qty),
                             tgl_exp=r.tgl_exp, sisa_hari=int(r.sisa_hari), proyeksi_laku=int(min(r.qty, round(demand))),
                             berisiko=ber, nilai_risiko=ber * float(r.hpp), hpp=float(r.hpp), harga=float(r.harga),
                             pemasok=r.pemasok, shelf_life=int(r.shelf_life), level=level_dari_hari(int(r.sisa_hari))))
    df = pd.DataFrame(rows)
    df["rekomendasi"] = df.apply(_rekom_singkat, axis=1)
    df["keputusan"] = df.batch_id.map(lambda x: store()["tindakan"].get(x, {}).get("keputusan", "Menunggu"))
    return df.sort_values(["sisa_hari", "berisiko"], ascending=[True, False]).reset_index(drop=True)


def _rekom_singkat(r) -> str:
    if r.berisiko <= 0:
        return "Pantau"
    if r.level == "Kritis":
        return "Diskon agresif (min. HPP) + pindah rak depan"
    if r.level == "Siaga":
        return "Bundling dengan fast-moving" if r.shelf_life > 30 else "Diskon bertahap"
    if r.sisa_hari >= 21 and r.shelf_life >= 90:
        return "Retur ke pemasok"
    return "Diskon bertahap (min. HPP)"


def get_rekomendasi_tindakan(batch_id: str) -> dict:
    """-> dict(tindakan_utama, diskon_bertahap[list], bundling, retur_layak, harga_min)"""
    r = get_risiko_kedaluwarsa().set_index("batch_id").loc[batch_id]
    steps = []
    for ke, p in enumerate((10, 20, 30, 40), start=1):
        harga = max(r.hpp, round(r.harga * (1 - p / 100), -2))
        steps.append(dict(tahap=ke, diskon=p, harga=float(harga), margin=round((harga - r.hpp) / harga * 100, 1)))
    prod = stok_service.get_produk()
    stok = stok_service.get_stok_status().set_index("produk_id")
    cand = prod[(prod.kategori == r.kategori) & (prod.produk_id != r.produk_id)].copy()
    cand = cand[cand.produk_id.map(lambda x: stok.loc[x, "status"] != "Menipis")].sort_values("rata_harian", ascending=False)
    bundling = cand.iloc[0].nama if len(cand) else "-"
    return dict(tindakan_utama=r.rekomendasi, diskon_bertahap=steps, bundling=bundling,
                retur_layak=bool(r.sisa_hari >= 14 and r.shelf_life >= 60), harga_min=float(r.hpp), baris=r)


def proses_tindakan(batch_id: str, keputusan: str, tindakan: str, catatan: str, user: str) -> dict:
    """keputusan: Setujui | Tolak | Lainnya. Menyimpan harga diskon / bundling & tunda pemesanan."""
    r = get_risiko_kedaluwarsa().set_index("batch_id").loc[batch_id]
    store()["tindakan"][batch_id] = dict(keputusan="Ditolak" if keputusan == "Tolak" else "Disetujui", tindakan=tindakan,
                                         catatan=catatan, oleh=user, waktu=now(), nama=r.nama)
    if keputusan == "Tolak":
        return dict(ok=True, pesan="Rekomendasi ditolak dan dicatat.")
    if "iskon" in tindakan:
        rek = get_rekomendasi_tindakan(batch_id)["diskon_bertahap"][1]
        store()["diskon"][batch_id] = dict(persen=rek["diskon"], harga=rek["harga"])
        stok_service.tambah_tugas(f"Pasang label diskon {rek['diskon']}% batch {batch_id} ({r.nama})",
                                  f"Harga diskon Rp {rek['harga']:,.0f} (tidak di bawah HPP). Pindahkan ke rak depan.".replace(",", "."),
                                  "Label diskon", batch_id)
    elif "undling" in tindakan:
        stok_service.tambah_tugas(f"Siapkan bundling batch {batch_id} ({r.nama})", "Bundling dengan produk fast-moving sesuai keputusan Manajer.", "Bundling", batch_id)
    elif "etur" in tindakan:
        stok_service.tambah_tugas(f"Siapkan retur ke pemasok untuk batch {batch_id} ({r.nama})", "Kemas barang dan lampirkan berita acara retur.", "Retur pemasok", batch_id)
    else:
        stok_service.tambah_tugas(f"Tindakan batch {batch_id} ({r.nama}): {tindakan}", catatan or "-", "Lainnya", batch_id)
    store()["tunda"].add(int(r.produk_id))
    kirim_notifikasi("Staf Pembelian", "Risiko", f"Pemesanan {r.nama} ditunda karena batch {batch_id} berisiko kedaluwarsa.")
    return dict(ok=True, pesan="Keputusan disimpan. Tugas dikirim ke Staf Gudang dan pemesanan produk ditandai tunda.")
