"""
penjualan.py - penjualan dan FEFO (pemilik: Naila). Kontrak bagian 2.1 dan 4.

Isi:
  ambil_batch_fefo  langkah 1: baca batch urut FEFO
  bagi_ke_batch     langkah 2: hitung pembagian qty ke batch (di memori)
  simpan_penjualan_di  inti penjualan memakai sesi yang ada (dipakai impor_csv)
  simpan_penjualan  langkah 3: simpan ke database dalam satu transaksi
  ambil_harga_diskon  sambungan Wulan: harga diskon batch yang sudah disetujui pemilik
"""
from collections import OrderedDict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .models import (BatchStok, DetailPenjualan, MutasiStok, Produk,
                     RekomendasiTindakan, TransaksiPenjualan)


# ---------------------------------------------------------------- langkah 1
def ambil_batch_fefo(s: Session, produk_id: int, kunci: bool = False) -> list[BatchStok]:
    """
    Batch yang boleh dijual untuk satu produk, urut FEFO:
    kedaluwarsa paling dekat dulu.

    Syarat batch: status 'aktif' dan jumlah_sisa > 0.
    Kalau tanggal kedaluwarsa sama, batch dengan id lebih kecil didahulukan.
    kunci=True mengunci baris batch (PostgreSQL/Neon) selama transaksi berjalan,
    supaya dua penjualan bersamaan tidak mengambil stok yang sama.
    (SQLite mengabaikan kunci ini; tidak masalah untuk pemakaian lokal.)
    """
    q = (
        select(BatchStok)
        .where(
            BatchStok.produk_id == produk_id,
            BatchStok.status == "aktif",
            BatchStok.jumlah_sisa > 0,
        )
        .order_by(BatchStok.tgl_kedaluwarsa.asc(), BatchStok.id.asc())
    )
    if kunci:
        q = q.with_for_update()
    return list(s.execute(q).scalars())


# ---------------------------------------------------------------- langkah 2
def bagi_ke_batch(batches: list, qty: int) -> tuple[list[tuple], int]:
    """
    Hitung dari batch mana saja qty diambil. Murni hitungan di memori.

    batches : daftar batch yang SUDAH urut FEFO.
    qty     : jumlah yang dijual (bilangan bulat > 0).

    Return (alokasi, kurang)
      alokasi: daftar (batch, jumlah_diambil), hanya batch yang tersentuh.
      kurang : sisa kebutuhan yang tidak terpenuhi. 0 berarti stok cukup.
    """
    sisa_kebutuhan = qty
    alokasi = []
    for b in batches:
        if sisa_kebutuhan <= 0:
            break
        ambil = min(b.jumlah_sisa, sisa_kebutuhan)
        if ambil > 0:
            alokasi.append((b, ambil))
            sisa_kebutuhan -= ambil
    return alokasi, sisa_kebutuhan


# ------------------------------------------------- sambungan Wulan: harga diskon
def ambil_harga_diskon(s: Session, batch_ids: list) -> dict:
    """
    Harga diskon batch yang SUDAH DISETUJUI pemilik (tabel rekomendasi_tindakan,
    ditulis Wulan lewat setujui_tindakan). Return {batch_id: harga_diskon}.

    Hanya jenis 'diskon' berstatus 'disetujui' dengan harga_diskon > 0.
    Kalau satu batch punya beberapa persetujuan, yang paling baru dipakai.
    Batch tanpa diskon tidak muncul; pemakai memakai harga jual normal.
    """
    if not batch_ids:
        return {}
    baris = s.execute(
        select(RekomendasiTindakan.batch_id, RekomendasiTindakan.harga_diskon)
        .where(
            RekomendasiTindakan.batch_id.in_(batch_ids),
            RekomendasiTindakan.jenis == "diskon",
            RekomendasiTindakan.status == "disetujui",
            RekomendasiTindakan.harga_diskon.is_not(None),
            RekomendasiTindakan.harga_diskon > 0,
        )
        .order_by(RekomendasiTindakan.dibuat_pada.asc(), RekomendasiTindakan.id.asc())
    ).all()
    return {bid: int(harga) for bid, harga in baris}   # yang terakhir menimpa


# ---------------------------------------------------------------- langkah 3
class _Gagal(Exception):
    """Kesalahan yang pesannya boleh langsung dibaca pemilik."""


def _ke_tanggal(tanggal) -> date:
    if isinstance(tanggal, datetime):
        return tanggal.date()
    if isinstance(tanggal, date):
        return tanggal
    try:
        return datetime.strptime(str(tanggal), "%Y-%m-%d").date()
    except ValueError:
        raise _Gagal("Format tanggal harus YYYY-MM-DD")


def _rapikan_items(items) -> "OrderedDict[int, int]":
    """Validasi items, jumlahkan produk yang sama. Return {produk_id: qty}."""
    if not isinstance(items, (list, tuple)) or not items:
        raise _Gagal("Belum ada barang yang dijual")
    gabungan: "OrderedDict[int, int]" = OrderedDict()
    for it in items:
        try:
            pid, qty = int(it["produk_id"]), int(it["qty"])
        except (KeyError, TypeError, ValueError):
            raise _Gagal("Setiap barang harus punya produk_id dan qty berupa angka")
        if qty <= 0:
            raise _Gagal("Jumlah (qty) harus lebih dari 0")
        gabungan[pid] = gabungan.get(pid, 0) + qty
    return gabungan


def simpan_penjualan_di(s: Session, tgl: date, gabungan: "OrderedDict[int, int]") -> dict:
    """
    Inti penjualan FEFO memakai sesi yang sudah ada. TIDAK commit dan TIDAK rollback:
    pemanggil yang memutuskan (dipakai simpan_penjualan dan impor_csv penjualan).
    Kesalahan yang boleh dibaca pemilik dilempar sebagai _Gagal; kalau _Gagal
    terlempar, belum ada yang ditulis oleh pemanggilan ini.
    Return data penjualan: {"transaksi_id", "total", "rincian"}.
    """
    # --- Tahap A: hitung semua dulu, belum menulis apa pun ---
    rencana = []   # (produk, harga normal, alokasi, harga per batch)
    for pid, qty in gabungan.items():
        produk = s.get(Produk, pid)
        if produk is None:
            raise _Gagal(f"Produk dengan id {pid} tidak ditemukan")
        if produk.harga_jual is None:
            raise _Gagal(f"Harga jual {produk.nama} belum diatur")
        batches = ambil_batch_fefo(s, pid, kunci=True)
        alokasi, kurang = bagi_ke_batch(batches, qty)
        if kurang > 0:
            tersedia = qty - kurang
            raise _Gagal(f"Stok {produk.nama} tinggal {tersedia}, kurang {kurang}")
        harga_normal = int(produk.harga_jual)
        diskon = ambil_harga_diskon(s, [b.id for b, _ in alokasi])
        harga_batch = {b.id: min(diskon.get(b.id, harga_normal), harga_normal)
                       for b, _ in alokasi}
        rencana.append((produk, harga_normal, alokasi, harga_batch))

    # --- Tahap B: tulis semuanya ---
    total = sum(
        harga_batch[batch.id] * ambil
        for _, _, alokasi, harga_batch in rencana
        for batch, ambil in alokasi
    )
    trx = TransaksiPenjualan(tanggal=tgl, total=total)
    s.add(trx)
    s.flush()   # supaya trx.id terisi

    rincian = []
    for produk, harga, alokasi, harga_batch in rencana:
        dipakai = []
        for batch, ambil in alokasi:
            s.add(DetailPenjualan(
                transaksi_id=trx.id, produk_id=produk.id, batch_id=batch.id,
                qty=ambil, harga_satuan=harga_batch[batch.id],
                hpp_satuan=batch.hpp_satuan))
            s.add(MutasiStok(
                tanggal=tgl, produk_id=produk.id, batch_id=batch.id,
                jenis="penjualan", qty=-ambil,       # keluar = negatif
                keterangan=f"Penjualan #{trx.id}"))
            batch.jumlah_sisa -= ambil
            if batch.jumlah_sisa == 0:
                batch.status = "habis"
            dipakai.append({"batch_id": batch.id, "qty": ambil,
                            "harga_satuan": harga_batch[batch.id],
                            "tgl_kedaluwarsa": batch.tgl_kedaluwarsa})
        rincian.append({"produk_id": produk.id, "nama": produk.nama,
                        "qty": sum(d["qty"] for d in dipakai),
                        "harga_satuan": harga, "batch": dipakai})
    s.flush()
    return {"transaksi_id": trx.id, "total": total, "rincian": rincian}


def simpan_penjualan(tanggal, items: list[dict]) -> dict:
    """
    items: [{"produk_id": 1, "qty": 10}, ...]
    Harga satuan diambil dari produk.harga_jual; HPP dari batch yang tersentuh.
    Batch yang punya diskon DISETUJUI (rekomendasi_tindakan) dijual dengan harga
    diskonnya, tidak pernah lebih mahal dari harga jual normal.

    Semua tersimpan, atau tidak ada yang tersimpan (rollback).
    Tidak pernah memunculkan exception ke layar (kontrak bagian 6).
    """
    try:
        tgl = _ke_tanggal(tanggal)
        gabungan = _rapikan_items(items)

        with get_session() as s:
            try:
                data = simpan_penjualan_di(s, tgl, gabungan)
                s.commit()
                return {"ok": True, "pesan": "Penjualan tersimpan", "data": data}
            except Exception:
                s.rollback()
                raise
    except _Gagal as e:
        return {"ok": False, "pesan": str(e), "data": None}
    except Exception as e:
        return {"ok": False,
                "pesan": f"Gagal menyimpan penjualan ({type(e).__name__})",
                "data": None}
