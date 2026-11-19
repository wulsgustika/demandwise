"""Pembacaan data mentah dari database untuk modul analitik."""
import numpy as np
import pandas as pd

from . import _db


def produk_aktif() -> pd.DataFrame:
    df = _db.baca("""
        SELECT p.id AS produk_id, p.kode, p.nama AS nama_produk, p.kategori_id,
               k.nama AS kategori, p.satuan, p.pemasok_id, ps.nama AS pemasok,
               p.harga_beli_terakhir, p.harga_jual, p.umur_simpan_hari,
               p.lead_time_hari, p.aktif, p.tunda_pesan
        FROM produk p
        LEFT JOIN kategori k ON k.id = p.kategori_id
        LEFT JOIN pemasok ps ON ps.id = p.pemasok_id
        WHERE """ + _db.saring("p"))
    df["aktif"] = df["aktif"].astype(str).str.lower().isin(["1", "true", "t"])
    df["lead_time_hari"] = df["lead_time_hari"].fillna(1).astype(int).clip(lower=1)
    return df[df["aktif"]].reset_index(drop=True)


def semua_produk() -> pd.DataFrame:
    """Termasuk produk nonaktif (untuk label nama pada riwayat)."""
    return _db.baca("SELECT id AS produk_id, nama AS nama_produk FROM produk WHERE " + _db.saring())


def penjualan_harian_matriks():
    """Return (matriks tanggal x produk_id, qty/hari, nol-terisi; DatetimeIndex hari toko tutup)."""
    df = _db.baca("""
        SELECT t.tanggal, d.produk_id, SUM(d.qty) AS qty
        FROM detail_penjualan d JOIN transaksi_penjualan t ON t.id = d.transaksi_id
        WHERE """ + _db.saring("t") + """
        GROUP BY t.tanggal, d.produk_id""", tanggal=["tanggal"])
    buka = _db.baca("SELECT DISTINCT tanggal FROM transaksi_penjualan WHERE " + _db.saring(),
                    tanggal=["tanggal"])
    if df.empty:
        # Belum ada penjualan (mis. akun baru): matriks kosong tapi berindeks tanggal,
        # supaya perbandingan tanggal di modul lain tetap jalan (hasilnya kosong/nol, bukan error).
        return pd.DataFrame(index=pd.DatetimeIndex([], name="tanggal")), pd.DatetimeIndex([])
    pv = df.pivot_table(index="tanggal", columns="produk_id", values="qty", aggfunc="sum")
    kal = pd.date_range(pv.index.min(), pv.index.max(), freq="D")
    pv = pv.reindex(kal).fillna(0.0)
    pv.index.name = "tanggal"
    tutup = kal.difference(pd.DatetimeIndex(buka["tanggal"]))
    return pv, tutup


def events() -> pd.DataFrame:
    return _db.baca("SELECT id, nama, tgl_mulai, tgl_selesai, sumber FROM event_musiman "
                    "WHERE " + _db.saring() + " ORDER BY tgl_mulai", tanggal=["tgl_mulai", "tgl_selesai"])


def events_list() -> list:
    e = events()
    return [(r.nama, r.tgl_mulai, r.tgl_selesai) for r in e.itertuples()]


def koreksi_terbaru() -> pd.DataFrame:
    """Koreksi terakhir per (produk, tanggal)."""
    df = _db.baca("SELECT id, produk_id, tanggal_target, qty_koreksi, alasan, dibuat_pada "
                  "FROM koreksi_prediksi WHERE " + _db.saring() + " ORDER BY id", tanggal=["tanggal_target"])
    if df.empty:
        return df
    return df.drop_duplicates(["produk_id", "tanggal_target"], keep="last")


def prediksi_tersimpan(terapkan_koreksi: bool = True) -> pd.DataFrame:
    """produk_id, tanggal, qty_prediksi, model (+koreksi pemilik bila diminta)."""
    df = _db.baca("SELECT produk_id, tanggal_target AS tanggal, qty_prediksi, model, dibuat_pada "
                  "FROM hasil_prediksi WHERE " + _db.saring(), tanggal=["tanggal", "dibuat_pada"])
    if df.empty:
        return df
    df = df.sort_values("dibuat_pada").drop_duplicates(["produk_id", "tanggal"], keep="last")
    if terapkan_koreksi:
        kor = koreksi_terbaru()
        if not kor.empty:
            m = df.merge(kor[["produk_id", "tanggal_target", "qty_koreksi"]],
                         left_on=["produk_id", "tanggal"], right_on=["produk_id", "tanggal_target"],
                         how="left")
            df["qty_prediksi"] = np.where(m["qty_koreksi"].notna(), m["qty_koreksi"].to_numpy(),
                                          df["qty_prediksi"].to_numpy())
    return df.sort_values(["produk_id", "tanggal"]).reset_index(drop=True)


def batch_aktif() -> pd.DataFrame:
    return _db.baca("""
        SELECT id AS batch_id, produk_id, tgl_masuk, tgl_kedaluwarsa, jumlah_awal,
               jumlah_sisa, hpp_satuan, status
        FROM batch_stok WHERE jumlah_sisa > 0 AND status = 'aktif' AND """ + _db.saring(),
                    tanggal=["tgl_masuk", "tgl_kedaluwarsa"])
