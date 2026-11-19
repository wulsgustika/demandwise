"""backend/input_data.py - fungsi fondasi dan input KONTRAK 2.1 (awalnya milik Nadia, kini Naila).

Pola sama dengan modul lain: fungsi akhiran _di(s, ...) memakai sesi yang sudah
ada (mudah dites), fungsi tanpa akhiran membuka sesinya sendiri untuk dipakai Dhea.
"""
import io
from collections import OrderedDict
from datetime import date, datetime

import pandas as pd
from sqlalchemy import func, select

from .models import (BatchStok, BiayaOperasional, HargaJual, Kategori, MutasiStok,
                     Notifikasi, Pemasok, Produk, StockOpname, Writeoff)

# ---------------------------------------------------------------------------
# Langkah 1: get_produk
# ---------------------------------------------------------------------------
KOLOM_PRODUK = [
    "produk_id", "kode", "nama_produk", "kategori", "satuan", "pemasok",
    "harga_beli_terakhir", "harga_jual", "umur_simpan_hari", "lead_time_hari",
    "aktif", "tunda_pesan",
]


def get_produk_di(s, aktif_saja: bool = True) -> pd.DataFrame:
    """Daftar produk, diurutkan menurut nama.

    Kategori dan pemasok ditampilkan sebagai NAMA (bukan id). Produk tanpa
    kategori/pemasok tetap muncul dengan nilai kosong. Hasil kosong tetap
    berkolom lengkap.
    """
    q = (
        select(
            Produk.id, Produk.kode, Produk.nama, Kategori.nama, Produk.satuan,
            Pemasok.nama, Produk.harga_beli_terakhir, Produk.harga_jual,
            Produk.umur_simpan_hari, Produk.lead_time_hari, Produk.aktif,
            Produk.tunda_pesan,
        )
        .outerjoin(Kategori, Kategori.id == Produk.kategori_id)
        .outerjoin(Pemasok, Pemasok.id == Produk.pemasok_id)
        .order_by(Produk.nama, Produk.id)
    )
    if aktif_saja:
        q = q.where(Produk.aktif.is_(True))
    baris = [tuple(r) for r in s.execute(q).all()]
    return pd.DataFrame(baris, columns=KOLOM_PRODUK)


def get_produk(aktif_saja: bool = True) -> pd.DataFrame:
    """Fungsi KONTRAK 2.1 (dipakai semua modul). Membuka sesi sendiri."""
    from .db import get_session
    with get_session() as s:
        return get_produk_di(s, aktif_saja)


# ---------------------------------------------------------------------------
# Langkah 2: get_batch
# ---------------------------------------------------------------------------
KOLOM_BATCH = [
    "batch_id", "produk_id", "nama_produk", "tgl_masuk", "tgl_kedaluwarsa",
    "jumlah_awal", "jumlah_sisa", "hpp_satuan", "status",
]


def get_batch_di(s, produk_id=None, aktif_saja: bool = True) -> pd.DataFrame:
    """Daftar batch stok, urutan FEFO (kedaluwarsa terdekat dulu).

    produk_id=None berarti semua produk. aktif_saja=True hanya batch berstatus
    'aktif'. Hasil kosong tetap berkolom lengkap.
    """
    q = (
        select(
            BatchStok.id, BatchStok.produk_id, Produk.nama, BatchStok.tgl_masuk,
            BatchStok.tgl_kedaluwarsa, BatchStok.jumlah_awal, BatchStok.jumlah_sisa,
            BatchStok.hpp_satuan, BatchStok.status,
        )
        .join(Produk, Produk.id == BatchStok.produk_id)
        .order_by(BatchStok.tgl_kedaluwarsa, BatchStok.id)
    )
    if produk_id is not None:
        q = q.where(BatchStok.produk_id == produk_id)
    if aktif_saja:
        q = q.where(BatchStok.status == "aktif")
    baris = [tuple(r) for r in s.execute(q).all()]
    return pd.DataFrame(baris, columns=KOLOM_BATCH)


def get_batch(produk_id=None, aktif_saja: bool = True) -> pd.DataFrame:
    """Fungsi KONTRAK 2.1 (dipakai semua modul). Membuka sesi sendiri."""
    from .db import get_session
    with get_session() as s:
        return get_batch_di(s, produk_id, aktif_saja)


# ---------------------------------------------------------------------------
# Langkah 3: get_notifikasi
# ---------------------------------------------------------------------------
KOLOM_NOTIF = [
    "notif_id", "jenis", "level", "judul", "pesan", "dibaca", "dibuat_pada",
    "ref_tabel", "ref_id",
]


def get_notifikasi_di(s, belum_dibaca: bool = False) -> pd.DataFrame:
    """Daftar notifikasi, yang terbaru di atas.

    belum_dibaca=True hanya yang belum ditandai dibaca. Kolom id bernama
    `notif_id`, sama dengan nama yang dikembalikan kirim_notifikasi dan dipakai
    tandai_dibaca. Hasil kosong tetap berkolom lengkap.
    """
    q = (
        select(
            Notifikasi.id, Notifikasi.jenis, Notifikasi.level, Notifikasi.judul,
            Notifikasi.pesan, Notifikasi.dibaca, Notifikasi.dibuat_pada,
            Notifikasi.ref_tabel, Notifikasi.ref_id,
        )
        .order_by(Notifikasi.dibuat_pada.desc(), Notifikasi.id.desc())
    )
    if belum_dibaca:
        q = q.where(Notifikasi.dibaca.is_(False))
    baris = [tuple(r) for r in s.execute(q).all()]
    return pd.DataFrame(baris, columns=KOLOM_NOTIF)


def get_notifikasi(belum_dibaca: bool = False) -> pd.DataFrame:
    """Fungsi KONTRAK 2.1 (dipakai Dhea). Membuka sesi sendiri."""
    from .db import get_session
    with get_session() as s:
        return get_notifikasi_di(s, belum_dibaca)


# ---------------------------------------------------------------------------
# Langkah 4: tandai_dibaca
# ---------------------------------------------------------------------------
def tandai_dibaca_di(s, notif_id) -> dict:
    """Tandai satu notifikasi sebagai sudah dibaca (commit dilakukan pemanggil).

    Aman dipanggil berulang: notifikasi yang sudah dibaca tetap ok=True.
    """
    if isinstance(notif_id, bool) or not isinstance(notif_id, int):
        return {"ok": False, "pesan": "ID notifikasi harus bilangan bulat", "data": None}
    n = s.get(Notifikasi, notif_id)
    if n is None:
        return {"ok": False, "pesan": "Notifikasi tidak ditemukan", "data": None}
    if n.dibaca:
        return {"ok": True, "pesan": "Notifikasi sudah ditandai dibaca",
                "data": {"notif_id": n.id}}
    n.dibaca = True
    s.flush()
    return {"ok": True, "pesan": "Notifikasi ditandai dibaca", "data": {"notif_id": n.id}}


def tandai_dibaca(notif_id) -> dict:
    """Fungsi KONTRAK 2.1. Membuka sesi sendiri."""
    from .db import get_session
    try:
        with get_session() as s:
            hasil = tandai_dibaca_di(s, notif_id)
            if hasil["ok"]:
                s.commit()
            else:
                s.rollback()
            return hasil
    except Exception as e:
        return {"ok": False, "pesan": f"Gagal menandai notifikasi: {e}", "data": None}


# ===========================================================================
# BAGIAN NADIA (bagian 2): tulis stok, input master, biaya, impor CSV
# ===========================================================================
class _Gagal(Exception):
    """Kesalahan yang pesannya boleh langsung dibaca pemilik."""


def _ke_int(nilai, nama: str) -> int:
    """Bilangan bulat dari int, float bulat, atau teks angka (CSV). Bool ditolak."""
    if isinstance(nilai, bool):
        raise _Gagal(f"{nama} harus berupa angka bulat")
    try:
        if isinstance(nilai, str):
            teks = nilai.strip().replace(".", "") if nilai.strip().count(".") > 1 else nilai.strip()
            f = float(teks)
        else:
            f = float(nilai)
    except (TypeError, ValueError):
        raise _Gagal(f"{nama} harus berupa angka bulat")
    if f != f or f in (float("inf"), float("-inf")) or f != int(f):
        raise _Gagal(f"{nama} harus berupa angka bulat")
    return int(f)


def _ke_tgl(nilai, nama: str = "Tanggal") -> date:
    if isinstance(nilai, datetime):
        return nilai.date()
    if isinstance(nilai, date):
        return nilai
    try:
        return datetime.strptime(str(nilai).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise _Gagal(f"{nama} harus berformat YYYY-MM-DD")


def _teks_wajib(nilai, nama: str) -> str:
    teks = "" if nilai is None else str(nilai).strip()
    if not teks:
        raise _Gagal(f"{nama} wajib diisi")
    return teks


def _jalankan(fungsi_di, *args) -> dict:
    """Buka sesi, jalankan fungsi _di, commit kalau ok, rollback kalau tidak.
    Tidak pernah melempar error ke layar (KONTRAK bagian 6)."""
    from .db import get_session
    try:
        with get_session() as s:
            try:
                hasil = fungsi_di(s, *args)
                if hasil["ok"]:
                    s.commit()
                else:
                    s.rollback()
                return hasil
            except Exception:
                s.rollback()
                raise
    except Exception as e:
        return {"ok": False, "pesan": f"Gagal menyimpan ({type(e).__name__}): {e}", "data": None}


def _batch_fefo(s, produk_id, hanya_ada_sisa=True) -> list:
    """Batch aktif produk, urut FEFO (kedaluwarsa terdekat, lalu id terkecil)."""
    q = (select(BatchStok)
         .where(BatchStok.produk_id == produk_id, BatchStok.status == "aktif")
         .order_by(BatchStok.tgl_kedaluwarsa.asc(), BatchStok.id.asc()))
    if hanya_ada_sisa:
        q = q.where(BatchStok.jumlah_sisa > 0)
    return list(s.execute(q).scalars())


def _kurangi_batch(s, batch, qty, tgl, jenis, keterangan) -> None:
    """Kurangi satu batch + tulis mutasi bertanda negatif. Batch 0 -> 'habis'."""
    batch.jumlah_sisa -= qty
    if batch.jumlah_sisa == 0:
        batch.status = "habis"
    s.add(MutasiStok(tanggal=tgl, produk_id=batch.produk_id, batch_id=batch.id,
                     jenis=jenis, qty=-qty, keterangan=keterangan))


def _kurangi_fefo(s, produk_id, qty, tgl, jenis, keterangan) -> list:
    """Kurangi stok produk dari batch FEFO. Stok kurang -> _Gagal (belum menulis)."""
    batches = _batch_fefo(s, produk_id)
    tersedia = sum(b.jumlah_sisa for b in batches)
    if qty > tersedia:
        raise _Gagal(f"Stok tidak cukup: tersedia {tersedia}, diminta {qty}")
    sisa, dipakai = qty, []
    for b in batches:
        if sisa == 0:
            break
        ambil = min(b.jumlah_sisa, sisa)
        _kurangi_batch(s, b, ambil, tgl, jenis, keterangan)
        dipakai.append({"batch_id": b.id, "qty": ambil})
        sisa -= ambil
    return dipakai


# ---------------------------------------------------------------------------
# catat_retur  (retur KE PEMASOK: stok berkurang, sesuai data dummy Wulan)
# ---------------------------------------------------------------------------
def catat_retur_di(s, produk_id, qty, keterangan, tanggal) -> dict:
    """Retur ke pemasok. Karena fungsi tidak menerima batch_id, stok dikurangi
    dari batch FEFO (kedaluwarsa terdekat dulu). Mutasi 'retur' bertanda negatif."""
    try:
        pid = _ke_int(produk_id, "ID produk")
        jumlah = _ke_int(qty, "Jumlah retur")
        if jumlah <= 0:
            raise _Gagal("Jumlah retur harus lebih dari 0")
        ket = _teks_wajib(keterangan, "Keterangan retur")
        tgl = _ke_tgl(tanggal)
        if s.get(Produk, pid) is None:
            raise _Gagal("Produk tidak ditemukan")
        dipakai = _kurangi_fefo(s, pid, jumlah, tgl, "retur", ket)
        s.flush()
        return {"ok": True, "pesan": "Retur dicatat",
                "data": {"produk_id": pid, "qty": jumlah, "batch": dipakai}}
    except _Gagal as e:
        return {"ok": False, "pesan": str(e), "data": None}


def catat_retur(produk_id, qty, keterangan, tanggal) -> dict:
    """Fungsi KONTRAK 2.1."""
    return _jalankan(catat_retur_di, produk_id, qty, keterangan, tanggal)


# ---------------------------------------------------------------------------
# catat_barang_rusak
# ---------------------------------------------------------------------------
def catat_barang_rusak_di(s, produk_id, batch_id, qty, keterangan, tanggal) -> dict:
    try:
        pid = _ke_int(produk_id, "ID produk")
        bid = _ke_int(batch_id, "ID batch")
        jumlah = _ke_int(qty, "Jumlah rusak")
        if jumlah <= 0:
            raise _Gagal("Jumlah rusak harus lebih dari 0")
        ket = _teks_wajib(keterangan, "Keterangan")
        tgl = _ke_tgl(tanggal)
        b = s.get(BatchStok, bid)
        if b is None:
            raise _Gagal("Batch tidak ditemukan")
        if b.produk_id != pid:
            raise _Gagal("Batch ini bukan milik produk tersebut")
        if b.status != "aktif":
            raise _Gagal(f"Batch berstatus {b.status}, tidak bisa dikurangi")
        if jumlah > b.jumlah_sisa:
            raise _Gagal(f"Stok batch tinggal {b.jumlah_sisa}, kurang {jumlah - b.jumlah_sisa}")
        _kurangi_batch(s, b, jumlah, tgl, "rusak", ket)
        s.flush()
        return {"ok": True, "pesan": "Barang rusak dicatat",
                "data": {"batch_id": bid, "produk_id": pid, "qty": jumlah,
                         "sisa_batch": b.jumlah_sisa}}
    except _Gagal as e:
        return {"ok": False, "pesan": str(e), "data": None}


def catat_barang_rusak(produk_id, batch_id, qty, keterangan, tanggal) -> dict:
    """Fungsi KONTRAK 2.1."""
    return _jalankan(catat_barang_rusak_di, produk_id, batch_id, qty, keterangan, tanggal)


# ---------------------------------------------------------------------------
# catat_writeoff
# ---------------------------------------------------------------------------
def catat_writeoff_di(s, batch_id, qty, tanggal) -> dict:
    """Kerugian kedaluwarsa: total_rugi = qty x HPP batch. Mengisi tabel writeoff,
    mengurangi batch, mutasi 'writeoff', dan mengirim notifikasi 'writeoff_dicatat'."""
    from .notifikasi import kirim_notifikasi_di
    try:
        bid = _ke_int(batch_id, "ID batch")
        jumlah = _ke_int(qty, "Jumlah write-off")
        if jumlah <= 0:
            raise _Gagal("Jumlah write-off harus lebih dari 0")
        tgl = _ke_tgl(tanggal)
        b = s.get(BatchStok, bid)
        if b is None:
            raise _Gagal("Batch tidak ditemukan")
        if b.status == "habis" or b.jumlah_sisa <= 0:
            raise _Gagal("Batch sudah habis")
        if jumlah > b.jumlah_sisa:
            raise _Gagal(f"Stok batch tinggal {b.jumlah_sisa}, kurang {jumlah - b.jumlah_sisa}")
        produk = s.get(Produk, b.produk_id)
        hpp = int(b.hpp_satuan)
        total = jumlah * hpp
        w = Writeoff(tanggal=tgl, batch_id=b.id, produk_id=b.produk_id, qty=jumlah,
                     hpp_satuan=hpp, total_rugi=total)
        s.add(w)
        _kurangi_batch(s, b, jumlah, tgl, "writeoff", "Write-off kedaluwarsa")
        s.flush()
        nama = produk.nama if produk else f"produk {b.produk_id}"
        notif = kirim_notifikasi_di(
            s, "writeoff_dicatat", "info", f"Write-off {nama} tercatat",
            f"{jumlah} unit {nama} (batch {b.id}) dihapus dari stok. "
            f"Kerugian Rp {total:,}".replace(",", "."),
            ref_tabel="writeoff", ref_id=w.id)
        if not notif["ok"]:
            raise _Gagal(notif["pesan"])
        return {"ok": True, "pesan": "Write-off dicatat",
                "data": {"writeoff_id": w.id, "batch_id": b.id, "qty": jumlah,
                         "total_rugi": total}}
    except _Gagal as e:
        return {"ok": False, "pesan": str(e), "data": None}


def catat_writeoff(batch_id, qty, tanggal) -> dict:
    """Fungsi KONTRAK 2.1."""
    return _jalankan(catat_writeoff_di, batch_id, qty, tanggal)


# ---------------------------------------------------------------------------
# simpan_opname
# ---------------------------------------------------------------------------
def simpan_opname_di(s, tanggal, items) -> dict:
    """items: [{"produk_id": 1, "stok_fisik": 48}, ...]

    stok_sistem = jumlah_sisa semua batch aktif produk. selisih = fisik - sistem.
    Selisih negatif dikurangi dari batch FEFO; selisih positif ditambahkan ke batch
    aktif terbaru. Mutasi 'opname' bertanda. Semua item valid, atau tidak ada yang
    tersimpan."""
    try:
        tgl = _ke_tgl(tanggal)
        if not isinstance(items, (list, tuple)) or not items:
            raise _Gagal("Belum ada produk yang di-opname")
        rapi, terlihat = [], set()
        for it in items:
            try:
                pid, fisik = it["produk_id"], it["stok_fisik"]
            except (KeyError, TypeError):
                raise _Gagal("Setiap baris harus punya produk_id dan stok_fisik")
            pid, fisik = _ke_int(pid, "ID produk"), _ke_int(fisik, "Stok fisik")
            if fisik < 0:
                raise _Gagal("Stok fisik tidak boleh negatif")
            if pid in terlihat:
                raise _Gagal(f"Produk {pid} muncul lebih dari sekali")
            terlihat.add(pid)
            rapi.append((pid, fisik))

        hasil = []
        for pid, fisik in rapi:
            produk = s.get(Produk, pid)
            if produk is None:
                raise _Gagal(f"Produk dengan id {pid} tidak ditemukan")
            batches = _batch_fefo(s, pid, hanya_ada_sisa=False)
            sistem = sum(b.jumlah_sisa for b in batches)
            selisih = fisik - sistem
            if selisih > 0 and not batches:
                raise _Gagal(f"{produk.nama}: tidak ada batch aktif untuk menampung "
                             f"kelebihan stok, catat barang masuk dulu")
            s.add(StockOpname(tanggal=tgl, produk_id=pid, stok_sistem=sistem,
                              stok_fisik=fisik, selisih=selisih))
            if selisih < 0:
                _kurangi_fefo(s, pid, -selisih, tgl, "opname", "Selisih stock opname")
            elif selisih > 0:
                b = max(batches, key=lambda x: (x.tgl_masuk, x.id))
                b.jumlah_sisa += selisih
                s.add(MutasiStok(tanggal=tgl, produk_id=pid, batch_id=b.id, jenis="opname",
                                 qty=selisih, keterangan="Selisih stock opname"))
            hasil.append({"produk_id": pid, "stok_sistem": sistem, "stok_fisik": fisik,
                          "selisih": selisih})
        s.flush()
        return {"ok": True, "pesan": "Stock opname disimpan", "data": {"hasil": hasil}}
    except _Gagal as e:
        return {"ok": False, "pesan": str(e), "data": None}


def simpan_opname(tanggal, items) -> dict:
    """Fungsi KONTRAK 2.1."""
    return _jalankan(simpan_opname_di, tanggal, items)


# ---------------------------------------------------------------------------
# tambah_produk
# ---------------------------------------------------------------------------
WAJIB_PRODUK = ["kode", "nama", "kategori", "pemasok", "satuan", "harga_jual"]


def _cari_id(s, model, data, kunci_id, kunci_nama, label):
    """Cari kategori/pemasok lewat id (kategori_id/pemasok_id) atau nama.

    Pencarian otomatis terbatas pada data milik akun yang login (lihat backend/db.py).
    Akun pengguna (bukan demo) yang mengetik nama kategori/pemasok baru: dibuatkan
    otomatis untuk akunnya, karena akun baru memang mulai tanpa kategori/pemasok."""
    from .konteks import adalah_demo
    if data.get(kunci_id) not in (None, ""):
        obj = s.get(model, _ke_int(data[kunci_id], f"ID {label}"))
    else:
        nama = _teks_wajib(data.get(kunci_nama), label.capitalize())
        obj = s.execute(select(model).where(func.lower(model.nama) == nama.lower())).scalars().first()
        if obj is None and not adalah_demo():
            nama = " ".join(nama.split())
            obj = Kategori(nama=nama) if model is Kategori else Pemasok(nama=nama, lead_time_hari=1)
            s.add(obj)
            s.flush()
    if obj is None:
        raise _Gagal(f"{label.capitalize()} tidak ditemukan")
    return obj


def tambah_produk_di(s, data) -> dict:
    """data: kode, nama, kategori (nama) atau kategori_id, pemasok (nama) atau
    pemasok_id, satuan, harga_jual wajib. Opsional: harga_beli_terakhir,
    umur_simpan_hari, lead_time_hari (default: lead time pemasok). Kolom
    tunda_pesan milik Wulan, tidak disentuh."""
    try:
        if not isinstance(data, dict):
            raise _Gagal("Data produk harus berupa dict")
        for k in ("kode", "nama", "satuan", "harga_jual"):
            if data.get(k) in (None, ""):
                raise _Gagal(f"{k} wajib diisi")
        kode, nama = _teks_wajib(data["kode"], "Kode"), _teks_wajib(data["nama"], "Nama")
        satuan = _teks_wajib(data["satuan"], "Satuan")
        harga_jual = _ke_int(data["harga_jual"], "Harga jual")
        if harga_jual < 0:
            raise _Gagal("Harga jual tidak boleh negatif")
        opsi = {}
        for k, label in (("harga_beli_terakhir", "Harga beli"),
                         ("umur_simpan_hari", "Umur simpan"), ("lead_time_hari", "Lead time")):
            if data.get(k) not in (None, ""):
                v = _ke_int(data[k], label)
                if v < 0:
                    raise _Gagal(f"{label} tidak boleh negatif")
                opsi[k] = v
        kategori = _cari_id(s, Kategori, data, "kategori_id", "kategori", "kategori")
        pemasok = _cari_id(s, Pemasok, data, "pemasok_id", "pemasok", "pemasok")
        if s.execute(select(Produk.id).where(func.lower(Produk.kode) == kode.lower())).first():
            raise _Gagal(f"Kode produk {kode} sudah dipakai")
        opsi.setdefault("lead_time_hari", pemasok.lead_time_hari)
        p = Produk(kode=kode, nama=nama, kategori_id=kategori.id, satuan=satuan,
                   pemasok_id=pemasok.id, harga_jual=harga_jual, aktif=True, **opsi)
        s.add(p)
        s.flush()
        # Riwayat harga ikut dicatat (komentar models.py: keduanya harus selaras).
        s.add(HargaJual(produk_id=p.id, harga=harga_jual, berlaku_mulai=date.today(),
                        sumber="manual"))
        s.flush()
        return {"ok": True, "pesan": "Produk ditambahkan",
                "data": {"produk_id": p.id, "kode": kode}}
    except _Gagal as e:
        return {"ok": False, "pesan": str(e), "data": None}


def tambah_produk(data) -> dict:
    """Fungsi KONTRAK 2.1."""
    return _jalankan(tambah_produk_di, data)


# ---------------------------------------------------------------------------
# simpan_biaya
# ---------------------------------------------------------------------------
def simpan_biaya_di(s, tanggal, kategori_biaya, jumlah, keterangan=None) -> dict:
    """Satu baris biaya_operasional; dibaca get_laporan_laba."""
    try:
        tgl = _ke_tgl(tanggal)
        kat = _teks_wajib(kategori_biaya, "Kategori biaya")
        nilai = _ke_int(jumlah, "Jumlah biaya")
        if nilai <= 0:
            raise _Gagal("Jumlah biaya harus lebih dari 0")
        ket = None if keterangan is None or not str(keterangan).strip() else str(keterangan).strip()
        b = BiayaOperasional(tanggal=tgl, kategori_biaya=kat, jumlah=nilai, keterangan=ket)
        s.add(b)
        s.flush()
        return {"ok": True, "pesan": "Biaya disimpan",
                "data": {"biaya_id": b.id, "jumlah": nilai}}
    except _Gagal as e:
        return {"ok": False, "pesan": str(e), "data": None}


def simpan_biaya(tanggal, kategori_biaya, jumlah, keterangan=None) -> dict:
    """Fungsi KONTRAK 2.1."""
    return _jalankan(simpan_biaya_di, tanggal, kategori_biaya, jumlah, keterangan)


# ---------------------------------------------------------------------------
# impor_csv
# ---------------------------------------------------------------------------
KOLOM_IMPOR = {
    "produk": ["kode", "nama", "kategori", "pemasok", "satuan", "harga_jual"],
    "stok_awal": ["qty", "tgl_kedaluwarsa", "hpp_satuan"],      # + kode ATAU produk_id
    "penjualan": ["tanggal", "qty"],                            # + kode ATAU produk_id
}


def _baca_csv(file) -> pd.DataFrame:
    """file: path teks, bytes, atau objek file/upload (punya .read())."""
    if hasattr(file, "read"):
        isi = file.read()
        if hasattr(file, "seek"):
            try:
                file.seek(0)
            except Exception:
                pass
    elif isinstance(file, (bytes, bytearray)):
        isi = bytes(file)
    else:
        try:
            with open(file, "rb") as f:
                isi = f.read()
        except (OSError, TypeError):
            raise _Gagal("File CSV tidak ditemukan")
    if isinstance(isi, bytes):
        isi = isi.decode("utf-8-sig")
    try:
        df = pd.read_csv(io.StringIO(isi), dtype=str, keep_default_na=False, sep=None,
                         engine="python")
    except Exception:
        raise _Gagal("File CSV tidak bisa dibaca")
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _produk_id_dari_baris(s, baris) -> int:
    if str(baris.get("produk_id", "")).strip():
        pid = _ke_int(baris["produk_id"], "produk_id")
        if s.get(Produk, pid) is None:
            raise _Gagal(f"Produk dengan id {pid} tidak ditemukan")
        return pid
    kode = _teks_wajib(baris.get("kode"), "Kode produk")
    pid = s.execute(select(Produk.id).where(func.lower(Produk.kode) == kode.lower())).scalar()
    if pid is None:
        raise _Gagal(f"Produk dengan kode {kode} tidak ditemukan")
    return pid


def impor_csv_di(s, jenis, file) -> dict:
    """jenis: 'produk' | 'stok_awal' | 'penjualan'.

    SEMUA ATAU TIDAK SAMA SEKALI: kalau ada satu baris bermasalah, tidak ada yang
    disimpan dan semua baris bermasalah dilaporkan di data["gagal"] (nomor baris
    sesuai nomor baris di file; baris 1 adalah judul kolom).
    Penjualan memakai jalur FEFO yang sama dengan simpan_penjualan; satu transaksi
    per tanggal. Stok yang kurang membatalkan seluruh impor.
    """
    from .penjualan import _Gagal as _GagalJual, simpan_penjualan_di
    from .stok import catat_barang_masuk_di
    try:
        if jenis not in KOLOM_IMPOR:
            raise _Gagal(f"Jenis impor harus salah satu dari {list(KOLOM_IMPOR)}")
        df = _baca_csv(file)
        wajib = list(KOLOM_IMPOR[jenis])
        kurang = [k for k in wajib if k not in df.columns]
        if jenis != "produk" and "kode" not in df.columns and "produk_id" not in df.columns:
            kurang.append("kode (atau produk_id)")
        if kurang:
            raise _Gagal("Kolom wajib tidak ada: " + ", ".join(kurang))
        if df.empty:
            raise _Gagal("File CSV tidak berisi baris data")

        gagal, sukses = [], 0
        if jenis == "penjualan":
            kelompok: "OrderedDict[date, OrderedDict[int, int]]" = OrderedDict()
            nomor: dict = {}
            for i, baris in df.iterrows():
                n = i + 2
                try:
                    tgl = _ke_tgl(baris["tanggal"])
                    pid = _produk_id_dari_baris(s, baris)
                    qty = _ke_int(baris["qty"], "Jumlah")
                    if qty <= 0:
                        raise _Gagal("Jumlah harus lebih dari 0")
                except _Gagal as e:
                    gagal.append({"baris": n, "pesan": str(e)})
                    continue
                k = kelompok.setdefault(tgl, OrderedDict())
                k[pid] = k.get(pid, 0) + qty
                nomor.setdefault(tgl, []).append(n)
                sukses += 1
            if not gagal:
                for tgl in sorted(kelompok):
                    try:
                        simpan_penjualan_di(s, tgl, kelompok[tgl])
                    except _GagalJual as e:
                        gagal.append({"baris": ", ".join(map(str, nomor[tgl])),
                                      "pesan": f"Penjualan {tgl}: {e}"})
        else:
            for i, baris in df.iterrows():
                n = i + 2
                try:
                    if jenis == "produk":
                        hasil = tambah_produk_di(s, {k: baris.get(k, "") for k in (
                            "kode", "nama", "kategori", "pemasok", "satuan", "harga_jual",
                            "harga_beli_terakhir", "umur_simpan_hari", "lead_time_hari")})
                    else:
                        tgl = _ke_tgl(baris.get("tanggal") or date.today())
                        hasil = catat_barang_masuk_di(
                            s, _produk_id_dari_baris(s, baris), _ke_int(baris["qty"], "Jumlah"),
                            _ke_tgl(baris["tgl_kedaluwarsa"], "Tanggal kedaluwarsa"),
                            _ke_int(baris["hpp_satuan"], "HPP"), tgl)
                    if hasil["ok"]:
                        sukses += 1
                    else:
                        gagal.append({"baris": n, "pesan": hasil["pesan"]})
                except _Gagal as e:
                    gagal.append({"baris": n, "pesan": str(e)})
        if gagal:
            s.rollback()
            return {"ok": False,
                    "pesan": f"Impor dibatalkan: {len(gagal)} masalah ditemukan, tidak ada data yang disimpan",
                    "data": {"jenis": jenis, "gagal": gagal}}
        s.flush()
        return {"ok": True, "pesan": f"{sukses} baris berhasil diimpor",
                "data": {"jenis": jenis, "jumlah_baris": sukses, "gagal": []}}
    except _Gagal as e:
        s.rollback()
        return {"ok": False, "pesan": str(e), "data": None}


def impor_csv(jenis, file) -> dict:
    """Fungsi KONTRAK 2.1."""
    return _jalankan(impor_csv_di, jenis, file)
