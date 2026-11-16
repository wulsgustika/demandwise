"""Rekomendasi pembelian & alur pesanan: Staf Pembelian -> Manajer -> Pemilik -> pemasok (mock)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import stok_service
from .notifikasi_service import kirim_notifikasi
from .state import store, now, next_id

ALUR = ["Draf", "Review Manajer", "Persetujuan Pemilik", "Disetujui", "Dikirim ke Pemasok", "Jadwal Terkonfirmasi"]


def get_rekomendasi_pembelian() -> pd.DataFrame:
    """jumlah beli = prediksi lead time + safety stock - stok - pesanan berjalan
    batas maks = prediksi harian x sisa umur simpan.
    -> DataFrame[produk_id, nama, kategori, pemasok, stok, pred_lt, safety, berjalan, rekomendasi, maks_umur_simpan, disarankan, catatan]"""
    st_ = stok_service.get_stok_status()
    prod = stok_service.get_produk().set_index("produk_id")
    berjalan: dict[int, int] = {}
    for po in store()["pesanan"]:
        if po["status"] != "Revisi":
            for it in po["items"]:
                berjalan[it["produk_id"]] = berjalan.get(it["produk_id"], 0) + it["qty"]
    rows = []
    for r in st_.itertuples():
        bj = berjalan.get(r.produk_id, 0)
        rek = max(0, int(np.ceil(r.pred_lt + r.safety - r.stok - bj)))
        harian = r.pred_30 / 30
        maks = int(harian * float(prod.loc[r.produk_id, "shelf_life"]))
        tunda = r.produk_id in store()["tunda"]
        sar = 0 if tunda else min(rek, maks)
        cat = "Ditunda: ada batch berisiko kedaluwarsa" if tunda else ("Dibatasi masa simpan" if rek > maks else "")
        rows.append(dict(produk_id=r.produk_id, nama=r.nama, kategori=r.kategori, pemasok=r.pemasok, stok=r.stok,
                         pred_lt=round(r.pred_lt, 1), safety=r.safety, berjalan=bj, rekomendasi=rek, maks_umur_simpan=maks,
                         disarankan=sar, hpp=float(prod.loc[r.produk_id, "hpp"]), catatan=cat))
    return pd.DataFrame(rows)


def buat_draf(items: list[dict], user: str) -> dict:
    """items: [{produk_id, nama, pemasok, qty, hpp}] -> satu draf PO per pemasok."""
    by: dict[str, list] = {}
    for it in items:
        by.setdefault(it["pemasok"], []).append(dict(produk_id=int(it["produk_id"]), nama=it["nama"], qty=int(it["qty"]), hpp=float(it["hpp"])))
    ids = []
    for pem, its in by.items():
        po_id = f"PO-{next_id('po'):04d}"
        store()["pesanan"].insert(0, dict(id=po_id, pemasok=pem, status="Draf", dibuat_oleh=user, dibuat=now(), jadwal=None, items=its,
                                          log=[(now(), user, "Draf dibuat")]))
        ids.append(po_id)
    return dict(ok=True, pesan=f"{len(ids)} draf pesanan dibuat: {', '.join(ids)}. Ajukan ke Manajer untuk direview.", ids=ids)


def get_pesanan() -> list[dict]:
    return store()["pesanan"]


def nilai_po(po: dict) -> float:
    return sum(i["qty"] * i["hpp"] for i in po["items"])


_TRANSISI = {
    # aksi: (status asal, status tujuan, role, notifikasi ke, teks log)
    "ajukan": (("Draf", "Revisi"), "Review Manajer", "Staf Pembelian", "Manajer", "Diajukan ke Manajer"),
    "teruskan": (("Review Manajer",), "Persetujuan Pemilik", "Manajer", "Pemilik", "Diteruskan ke Pemilik"),
    "kembalikan": (("Review Manajer",), "Revisi", "Manajer", "Staf Pembelian", "Dikembalikan untuk revisi"),
    "setujui": (("Persetujuan Pemilik",), "Disetujui", "Pemilik", "Staf Pembelian", "Disetujui Pemilik"),
    "revisi": (("Persetujuan Pemilik",), "Revisi", "Pemilik", "Staf Pembelian", "Pemilik meminta revisi"),
    "kirim": (("Disetujui",), "Dikirim ke Pemasok", "Staf Pembelian", "Manajer", "Dikirim ke pemasok"),
    "konfirmasi_jadwal": (("Dikirim ke Pemasok",), "Jadwal Terkonfirmasi", "Staf Pembelian", "Manajer", "Jadwal kirim dikonfirmasi pemasok"),
}


def pesanan_aksi(po_id: str, aksi: str, user: dict, catatan: str = "", jadwal=None) -> dict:
    po = next((p for p in store()["pesanan"] if p["id"] == po_id), None)
    if po is None:
        return dict(ok=False, pesan="Pesanan tidak ditemukan.")
    asal, tujuan, role, notif_ke, teks = _TRANSISI[aksi]
    if user["role"] != role and user["role"] != "Manajer" or po["status"] not in asal:
        return dict(ok=False, pesan="Aksi tidak diizinkan untuk status/role ini.")
    po["status"] = tujuan
    if jadwal:
        po["jadwal"] = jadwal
        teks += f" ({jadwal:%d %b %Y})"
    po["log"].append((now(), user["nama"], teks + (f" - {catatan}" if catatan else "")))
    kirim_notifikasi(notif_ke, "Pesanan", f"{po_id} ({po['pemasok']}): {teks.lower()}.")
    return dict(ok=True, pesan=f"{po_id}: {teks}.")


def ubah_item(po_id: str, items: list[dict]) -> dict:
    po = next(p for p in store()["pesanan"] if p["id"] == po_id)
    if po["status"] not in ("Draf", "Revisi"):
        return dict(ok=False, pesan="Pesanan hanya dapat diubah saat Draf/Revisi.")
    po["items"] = items
    po["log"].append((now(), "Sistem", "Jumlah item diperbarui"))
    return dict(ok=True, pesan="Item pesanan diperbarui.")
