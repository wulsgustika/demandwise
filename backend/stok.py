"""backend/stok.py - barang masuk (KONTRAK 2.1, awalnya milik Nadia, kini Naila)."""
from datetime import date

from .models import BatchStok, MutasiStok, Produk


def catat_barang_masuk_di(s, produk_id, qty, tgl_kedaluwarsa, hpp_satuan, tanggal) -> dict:
    """Buat batch baru + mutasi 'masuk' (qty positif, KONTRAK: mutasi bertanda)."""
    if s.get(Produk, produk_id) is None:
        return {"ok": False, "pesan": "Produk tidak ditemukan", "data": None}
    if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
        return {"ok": False, "pesan": "Jumlah masuk harus bilangan bulat > 0", "data": None}
    if isinstance(hpp_satuan, bool) or not isinstance(hpp_satuan, int) or hpp_satuan < 0:
        return {"ok": False, "pesan": "HPP harus bilangan bulat >= 0", "data": None}
    if not isinstance(tanggal, date) or not isinstance(tgl_kedaluwarsa, date):
        return {"ok": False, "pesan": "Tanggal tidak valid", "data": None}
    if tgl_kedaluwarsa < tanggal:
        return {"ok": False, "pesan": "Tanggal kedaluwarsa tidak boleh sebelum tanggal masuk",
                "data": None}
    b = BatchStok(produk_id=produk_id, tgl_masuk=tanggal, tgl_kedaluwarsa=tgl_kedaluwarsa,
                  jumlah_awal=qty, jumlah_sisa=qty, hpp_satuan=hpp_satuan, status="aktif")
    s.add(b)
    s.flush()
    s.add(MutasiStok(tanggal=tanggal, produk_id=produk_id, batch_id=b.id, jenis="masuk",
                     qty=qty, keterangan="Barang masuk"))
    return {"ok": True, "pesan": "Barang masuk dicatat",
            "data": {"batch_id": b.id, "produk_id": produk_id, "qty": qty}}


def catat_barang_masuk(produk_id, qty, tgl_kedaluwarsa, hpp_satuan, tanggal) -> dict:
    """Fungsi KONTRAK 2.1."""
    from .db import get_session
    try:
        with get_session() as s:
            hasil = catat_barang_masuk_di(s, produk_id, qty, tgl_kedaluwarsa, hpp_satuan, tanggal)
            if hasil["ok"]:
                s.commit()
            else:
                s.rollback()
            return hasil
    except Exception as e:
        return {"ok": False, "pesan": f"Gagal mencatat barang masuk: {e}", "data": None}
