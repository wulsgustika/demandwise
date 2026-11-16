"""Stok, batch, penjualan (FEFO), retur, barang rusak, opname, write-off, tugas gudang (mock)."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import mock_data as md
from .ml import prediksi
from .notifikasi_service import kirim_notifikasi
from .state import store, now, next_id


# ------------------------------------------------------------------ master
def get_produk() -> pd.DataFrame:
    p = md.produk_df().copy()
    p["harga"] = p.produk_id.map(store()["harga"])
    return p


def get_batch() -> pd.DataFrame:
    b = store()["batch"].copy()
    b = b[b.qty > 0]
    p = get_produk()[["produk_id", "nama", "kategori", "hpp", "harga", "shelf_life", "pemasok", "rata_harian"]]
    b = b.merge(p, on="produk_id", how="left")
    b["sisa_hari"] = (pd.to_datetime(b.tgl_exp) - pd.Timestamp(md.TODAY)).dt.days
    return b.sort_values(["produk_id", "tgl_exp"]).reset_index(drop=True)


def get_stok() -> pd.Series:
    b = store()["batch"]
    return b.groupby("produk_id").qty.sum().reindex(md.produk_df().produk_id).fillna(0).astype(int)


def get_stok_status() -> pd.DataFrame:
    """-> DataFrame[produk_id, nama, kategori, stok, pred_30, pred_lt, safety, rop, cover_hari, status, nilai_stok]"""
    prod = get_produk().set_index("produk_id")
    sales = md.penjualan_harian_df()
    pred = prediksi.get_prediksi(None, 30)
    stok = get_stok()
    sigma = sales[sales.tanggal >= pd.Timestamp(md.TODAY) - pd.Timedelta(days=56)].groupby("produk_id").qty.std()
    rows = []
    for pid, r in prod.iterrows():
        pp = pred[pred.produk_id == pid].sort_values("tanggal")
        avg = max(float(pp.yhat.mean()), .1)
        lt = int(r.lead_time)
        pred_lt = float(pp.yhat.head(lt).sum())
        safety = int(np.ceil(1.65 * float(sigma.get(pid, 1)) * np.sqrt(lt)))
        rop = int(np.ceil(pred_lt + safety))
        s = int(stok.get(pid, 0))
        cover = s / avg
        status = "Menipis" if s <= rop else ("Overstock" if cover > 45 else "Aman")
        rows.append(dict(produk_id=pid, nama=r.nama, kategori=r.kategori, pemasok=r.pemasok, stok=s,
                         pred_30=float(pp.yhat.sum()), pred_lt=pred_lt, safety=safety, rop=rop,
                         cover_hari=round(cover, 1), status=status, nilai_stok=s * float(r.hpp), lead_time=lt))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ FEFO
def _fefo_kurangi(produk_id: int, qty: int) -> list[dict]:
    b = store()["batch"]
    rincian, sisa = [], qty
    idx = b[(b.produk_id == produk_id) & (b.qty > 0)].sort_values("tgl_exp").index
    for i in idx:
        if sisa <= 0:
            break
        ambil = int(min(sisa, b.at[i, "qty"]))
        b.at[i, "qty"] -= ambil
        sisa -= ambil
        rincian.append(dict(batch_id=b.at[i, "batch_id"], tgl_exp=b.at[i, "tgl_exp"], diambil=ambil))
    return rincian


def _mutasi(jenis: str, produk_id: int, qty: int, user: str, ket: str = "") -> None:
    store()["mutasi"].insert(0, dict(waktu=now(), jenis=jenis, produk_id=produk_id, qty=qty, oleh=user, keterangan=ket))


def simpan_penjualan(items: list[dict], metode: str, user: str) -> dict:
    """items: [{produk_id, qty}] -> dict(ok, pesan, total, rincian[FEFO])"""
    stok = get_stok()
    prod = get_produk().set_index("produk_id")
    for it in items:
        if it["qty"] > stok.get(it["produk_id"], 0):
            return dict(ok=False, pesan=f"Stok {prod.loc[it['produk_id'], 'nama']} tidak cukup.")
    total, rincian = 0.0, []
    for it in items:
        pid, q = int(it["produk_id"]), int(it["qty"])
        for r in _fefo_kurangi(pid, q):
            rincian.append(dict(produk=prod.loc[pid, "nama"], **r))
        sub = q * float(prod.loc[pid, "harga"])
        total += sub
        store()["penjualan_baru"].append(dict(tanggal=md.TODAY, produk_id=pid, qty=q, nilai=sub, hpp=q * float(prod.loc[pid, "hpp"])))
        _mutasi("penjualan", pid, -q, user, metode)
    return dict(ok=True, pesan="Transaksi tersimpan. Stok berkurang otomatis (FEFO).", total=total, rincian=rincian)


# ------------------------------------------------------------------ penerimaan / batch
def tambah_batch(produk_id: int, qty: int, tgl_exp: date, rak: str, user: str, jenis: str = "batch") -> dict:
    b = store()["batch"]
    bid = f"B{len(b) + 1:04d}"
    while bid in set(b.batch_id):
        bid = f"B{int(bid[1:]) + 1:04d}"
    store()["batch"] = pd.concat([b, pd.DataFrame([dict(batch_id=bid, produk_id=int(produk_id), qty=int(qty),
                                                         tgl_masuk=md.TODAY, tgl_exp=tgl_exp, rak=rak)])], ignore_index=True)
    _mutasi("barang_masuk" if jenis == "masuk" else "batch_baru", produk_id, qty, user, bid)
    return dict(ok=True, pesan=f"Batch {bid} berhasil dicatat ({qty} unit, kedaluwarsa {tgl_exp:%d %b %Y}).", batch_id=bid)


def retur(jenis: str, produk_id: int, qty: int, batch_id: str | None, alasan: str, user: str) -> dict:
    """jenis: 'Dari pelanggan' (stok bertambah) | 'Ke pemasok' (stok berkurang)."""
    b = store()["batch"]
    if jenis == "Ke pemasok":
        i = b.index[b.batch_id == batch_id]
        if len(i) == 0 or b.at[i[0], "qty"] < qty:
            return dict(ok=False, pesan="Jumlah retur melebihi stok batch.")
        b.at[i[0], "qty"] -= qty
        _mutasi("retur_pemasok", produk_id, -qty, user, alasan)
        return dict(ok=True, pesan=f"Retur ke pemasok dicatat: {qty} unit dari batch {batch_id}.")
    i = b.index[b.batch_id == batch_id]
    if len(i):
        b.at[i[0], "qty"] += qty
    _mutasi("retur_pelanggan", produk_id, qty, user, alasan)
    return dict(ok=True, pesan=f"Retur pelanggan dicatat: +{qty} unit dikembalikan ke stok.")


def barang_rusak(produk_id: int, batch_id: str, qty: int, penyebab: str, user: str) -> dict:
    b = store()["batch"]
    i = b.index[b.batch_id == batch_id]
    if len(i) == 0 or b.at[i[0], "qty"] < qty:
        return dict(ok=False, pesan="Jumlah rusak melebihi stok batch.")
    b.at[i[0], "qty"] -= qty
    _mutasi("barang_rusak", produk_id, -qty, user, penyebab)
    return dict(ok=True, pesan=f"Barang rusak dicatat: {qty} unit (stok berkurang).")


def get_mutasi(limit: int = 15) -> pd.DataFrame:
    m = pd.DataFrame(store()["mutasi"][:limit])
    if m.empty:
        return m
    return m.merge(md.produk_df()[["produk_id", "nama"]], on="produk_id", how="left")[["waktu", "jenis", "nama", "qty", "oleh", "keterangan"]]


# ------------------------------------------------------------------ opname
def get_stok_sistem() -> pd.DataFrame:
    p = get_produk()[["produk_id", "kode", "nama", "kategori", "hpp"]].copy()
    p["stok_sistem"] = p.produk_id.map(get_stok()).astype(int)
    return p


def simpan_opname(rows: list[dict], user: str) -> dict:
    """rows: [{produk_id, fisik}] -> dict(ok, pesan, selisih_item, nilai)"""
    prod = md.produk_df().set_index("produk_id")
    sistem = get_stok()
    n, nilai = 0, 0.0
    for r in rows:
        pid, fisik = int(r["produk_id"]), int(r["fisik"])
        sel = fisik - int(sistem[pid])
        if sel == 0:
            continue
        if sel < 0:
            _fefo_kurangi(pid, -sel)
        else:
            b = store()["batch"]
            cand = b[b.produk_id == pid].sort_values("tgl_exp")
            if len(cand):
                b.at[cand.index[-1], "qty"] += sel
        n += 1
        nilai += sel * float(prod.loc[pid, "hpp"])
        store()["opname_log"].insert(0, dict(waktu=now(), produk=prod.loc[pid, "nama"], sistem=int(sistem[pid]), fisik=fisik, selisih=sel, oleh=user))
        _mutasi("opname", pid, sel, user, "Penyesuaian stock opname")
    if n:
        kirim_notifikasi("Manajer", "Stok", f"Stock opname selesai: {n} produk memiliki selisih (nilai {nilai:,.0f}).".replace(",", "."))
    return dict(ok=True, pesan=f"Opname tersimpan. {n} produk disesuaikan.", n=n, nilai=nilai)


def get_opname_log() -> pd.DataFrame:
    return pd.DataFrame(store()["opname_log"], columns=["waktu", "produk", "sistem", "fisik", "selisih", "oleh"])


# ------------------------------------------------------------------ write-off
def catat_writeoff(batch_id: str, qty: int, alasan: str, user: str) -> dict:
    b = store()["batch"]
    i = b.index[b.batch_id == batch_id]
    if len(i) == 0 or b.at[i[0], "qty"] < qty:
        return dict(ok=False, pesan="Jumlah melebihi stok batch.")
    pid = int(b.at[i[0], "produk_id"])
    p = md.produk_df().set_index("produk_id").loc[pid]
    b.at[i[0], "qty"] -= qty
    store()["writeoff"].insert(0, dict(id=next_id("wo"), tanggal=md.TODAY, produk_id=pid, nama=p.nama, batch_id=batch_id, qty=int(qty),
                                       hpp=float(p.hpp), alasan=alasan, oleh=user))
    _mutasi("writeoff", pid, -qty, user, alasan)
    kirim_notifikasi("Manajer", "Stok", f"Write-off {qty} unit {p.nama} (batch {batch_id}) senilai {qty * p.hpp:,.0f}.".replace(",", "."))
    return dict(ok=True, pesan=f"Write-off dicatat: {qty} unit x HPP = Rp {qty * p.hpp:,.0f}".replace(",", "."))


def get_writeoff() -> pd.DataFrame:
    w = pd.DataFrame(store()["writeoff"])
    if w.empty:
        return pd.DataFrame(columns=["id", "tanggal", "produk_id", "nama", "batch_id", "qty", "hpp", "alasan", "oleh", "nilai"])
    w["nilai"] = w.qty * w.hpp
    return w


# ------------------------------------------------------------------ tugas gudang
def get_tugas() -> pd.DataFrame:
    return pd.DataFrame(store()["tugas"])


def tambah_tugas(judul: str, detail: str, jenis: str, batch_id: str = "-") -> None:
    store()["tugas"].insert(0, dict(id=next_id("tugas"), judul=judul, detail=detail, jenis=jenis, batch_id=batch_id,
                                    status="Belum", dibuat=now(), selesai=None))
    kirim_notifikasi("Staf Gudang", "Tugas", f"Tugas baru: {judul}")


def selesaikan_tugas(tugas_id: int, user: str) -> None:
    for t in store()["tugas"]:
        if t["id"] == tugas_id:
            t["status"], t["selesai"] = "Selesai", now()
            kirim_notifikasi("Manajer", "Tugas", f"{user} menyelesaikan tugas: {t['judul']}")
