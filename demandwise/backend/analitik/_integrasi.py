"""
Penghubung ke fungsi milik rekan (dipanggil seperlunya, dengan cadangan lokal):
  * kirim_notifikasi  (Nadia)  -> cadangan: tulis langsung ke tabel notifikasi
  * get_laporan_laba  (Naila)  -> cadangan: hitung sendiri dengan rumus KONTRAK 3.7
Lokasi modul bisa diatur di backend/konfig.py (MODUL_NOTIFIKASI_NADIA, MODUL_LABA_NAILA).
"""
import importlib
import logging

import pandas as pd

from . import _db, k

log = logging.getLogger("demandwise.analitik")

_cache = {}


def _cari(daftar_modul, nama):
    kunci = (tuple(daftar_modul), nama)
    if kunci in _cache:
        return _cache[kunci]
    ketemu = None
    for m in daftar_modul:
        try:
            fn = getattr(importlib.import_module(m), nama, None)
        except Exception:
            continue
        # jangan menunjuk ke diri sendiri
        if callable(fn) and not str(getattr(fn, "__module__", "")).startswith("backend.analitik"):
            ketemu = fn
            break
    if ketemu is None:
        log.warning("%s milik rekan tidak ditemukan di %s, memakai cadangan lokal. "
                    "Isi MODUL_* di backend/konfig.py kalau modulnya sudah ada.", nama, list(daftar_modul))
    _cache[kunci] = ketemu
    return ketemu


# ---------------------------------------------------------------------------
# Notifikasi
# ---------------------------------------------------------------------------
def notifikasi_sudah_ada(jenis, ref_tabel=None, ref_id=None, judul=None, hanya_belum_dibaca=False) -> bool:
    sql = "SELECT COUNT(*) AS n FROM notifikasi WHERE jenis = :j"
    p = {"j": jenis}
    if ref_tabel is not None:
        sql += " AND ref_tabel = :rt AND ref_id = :ri"
        p.update(rt=ref_tabel, ri=ref_id)
    if judul is not None:
        sql += " AND judul = :jd"
        p["jd"] = judul
    df = _db.baca(sql, p)
    if hanya_belum_dibaca:
        sql2 = sql + " AND (dibaca = :f OR dibaca IS NULL)"
        df = _db.baca(sql2, {**p, "f": False})
    return int(df["n"].iloc[0]) > 0


def kirim(jenis, level, judul, pesan, ref_tabel=None, ref_id=None, dedupe="belum_dibaca") -> bool:
    """Kirim notifikasi. dedupe: 'belum_dibaca' | 'semua' | None.  Return True kalau benar-benar terkirim."""
    if dedupe in ("belum_dibaca", "semua"):
        if notifikasi_sudah_ada(jenis, ref_tabel, ref_id, judul, hanya_belum_dibaca=(dedupe == "belum_dibaca")):
            return False
    fn = _cari(k.MODUL_NOTIFIKASI_NADIA, "kirim_notifikasi")
    if fn is not None:
        try:
            r = fn(jenis, level, judul, pesan, ref_tabel, ref_id)
            if not isinstance(r, dict) or r.get("ok", True):
                return True
        except Exception:
            pass  # jatuh ke cadangan
    _db.sisip(_db.T_NOTIFIKASI, [{
        "jenis": jenis, "level": level, "judul": judul, "pesan": pesan, "dibaca": False,
        "dibuat_pada": _db.sekarang(), "ref_tabel": ref_tabel,
        "ref_id": None if ref_id is None else int(ref_id)}])
    return True


# ---------------------------------------------------------------------------
# Laporan laba
# ---------------------------------------------------------------------------
URUTAN_LABA = ["Penjualan", "HPP", "Laba Kotor", "Biaya Operasional",
               "Kerugian Kedaluwarsa (Write-off)", "Laba Bersih"]


def laba_sendiri(tgl_awal, tgl_akhir) -> pd.DataFrame:
    """Rumus KONTRAK 3.7: laba bersih = penjualan - HPP - biaya operasional - write-off."""
    p = {"a": _db.iso(tgl_awal), "b": _db.iso(tgl_akhir)}
    j = _db.baca("""SELECT COALESCE(SUM(d.qty*d.harga_satuan),0) AS penjualan,
                           COALESCE(SUM(d.qty*d.hpp_satuan),0) AS hpp
                    FROM detail_penjualan d JOIN transaksi_penjualan t ON t.id = d.transaksi_id
                    WHERE t.tanggal >= :a AND t.tanggal <= :b""", p)
    bo = _db.baca("SELECT COALESCE(SUM(jumlah),0) AS v FROM biaya_operasional "
                  "WHERE tanggal >= :a AND tanggal <= :b", p)["v"].iloc[0]
    wo = _db.baca("SELECT COALESCE(SUM(total_rugi),0) AS v FROM writeoff "
                  "WHERE tanggal >= :a AND tanggal <= :b", p)["v"].iloc[0]
    pen, hpp = float(j["penjualan"].iloc[0]), float(j["hpp"].iloc[0])
    kotor = pen - hpp
    bersih = kotor - float(bo) - float(wo)
    return pd.DataFrame({"komponen": URUTAN_LABA,
                         "jumlah": [pen, hpp, kotor, float(bo), float(wo), bersih]})


def laporan_laba(tgl_awal, tgl_akhir) -> pd.DataFrame:
    """Pakai get_laporan_laba milik Naila bila sudah ada, kalau tidak hitung sendiri."""
    fn = _cari(k.MODUL_LABA_NAILA, "get_laporan_laba")
    if fn is not None:
        try:
            df = fn(tgl_awal, tgl_akhir)
            if isinstance(df, pd.DataFrame) and not df.empty and {"komponen", "jumlah"} <= set(df.columns):
                return df
        except Exception:
            pass
    return laba_sendiri(tgl_awal, tgl_akhir)
