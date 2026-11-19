"""
models.py - skema database DemandWise (pemilik: Naila).

Sumber kebenaran: KONTRAK.md bagian 1. Jangan ubah nama tabel/kolom tanpa
mengabari pemilik dan pemakainya, lalu catat di Riwayat Perubahan.

Satu file ini jalan di PostgreSQL (Neon/Supabase) dan SQLite lokal.

Catatan desain:
- Uang disimpan BigInteger (rupiah bulat). Dipilih ketimbang NUMERIC(14,0)
  karena di SQLite NUMERIC dibaca sebagai Decimal dan lambat di pandas.
  Di PostgreSQL BIGINT tetap muat jauh di atas 14 digit.
- Kolom pilihan (status, jenis, level, sumber) memakai String + CheckConstraint,
  bukan tipe ENUM, supaya mudah diubah tanpa migrasi tipe di PostgreSQL.
- mutasi_stok.qty BERTANDA: masuk/opname-lebih positif; penjualan, retur,
  rusak, writeoff, opname-kurang negatif (sesuai data dummy Wulan).
"""
from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _in(kolom: str, nilai: list[str]) -> str:
    """Teks CHECK: kolom IN ('a','b',...)."""
    return f"{kolom} IN ({', '.join(repr(v) for v in nilai)})"


# Nilai pilihan, persis seperti kontrak
STATUS_BATCH = ["aktif", "habis", "kedaluwarsa"]
JENIS_MUTASI = ["masuk", "retur", "rusak", "opname", "penjualan", "writeoff"]
LEVEL_NOTIF = ["info", "waspada", "siaga", "kritis"]
JENIS_REKOMENDASI = ["diskon", "bundling", "retur_pemasok", "lainnya"]
STATUS_REKOMENDASI = ["menunggu", "disetujui", "ditolak", "tindakan_lain"]
STATUS_PESANAN = ["draf", "dipesan", "dikirim", "diterima", "dibatalkan"]
SUMBER_HARGA = ["rekomendasi", "manual"]
SUMBER_EVENT = ["auto", "manual"]


def _pk() -> Mapped[int]:
    return mapped_column(Integer, primary_key=True, autoincrement=True)


# --------------------------------------------------------------------------
# Master
# --------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = _pk()
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nama_usaha: Mapped[str] = mapped_column(String(150), nullable=False)
    dibuat_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)


class Kategori(Base):
    __tablename__ = "kategori"
    id: Mapped[int] = _pk()
    nama: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class Pemasok(Base):
    __tablename__ = "pemasok"
    id: Mapped[int] = _pk()
    nama: Mapped[str] = mapped_column(String(150), nullable=False)
    kontak: Mapped[str | None] = mapped_column(String(100))
    lead_time_hari: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (CheckConstraint("lead_time_hari >= 0", name="ck_pemasok_lead_time"),)


class Produk(Base):
    __tablename__ = "produk"
    id: Mapped[int] = _pk()
    kode: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    nama: Mapped[str] = mapped_column(String(150), nullable=False)
    kategori_id: Mapped[int | None] = mapped_column(ForeignKey("kategori.id"))
    satuan: Mapped[str | None] = mapped_column(String(30))
    pemasok_id: Mapped[int | None] = mapped_column(ForeignKey("pemasok.id"))
    harga_beli_terakhir: Mapped[int | None] = mapped_column(BigInteger)
    # Harga jual yang BERLAKU sekarang. Riwayatnya ada di tabel harga_jual;
    # keduanya harus diperbarui bersamaan (setujui_harga / ubah_harga_manual).
    harga_jual: Mapped[int | None] = mapped_column(BigInteger)
    umur_simpan_hari: Mapped[int | None] = mapped_column(Integer)
    lead_time_hari: Mapped[int | None] = mapped_column(Integer)
    aktif: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Ditulis Wulan saat tindakan batch berisiko disetujui; dibaca Naila di draf pesanan.
    tunda_pesan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    kategori: Mapped["Kategori"] = relationship()
    pemasok: Mapped["Pemasok"] = relationship()

    __table_args__ = (
        Index("ix_produk_kategori_id", "kategori_id"),
        Index("ix_produk_pemasok_id", "pemasok_id"),
    )


# --------------------------------------------------------------------------
# Stok dan penjualan
# --------------------------------------------------------------------------
class BatchStok(Base):
    __tablename__ = "batch_stok"
    id: Mapped[int] = _pk()
    produk_id: Mapped[int] = mapped_column(ForeignKey("produk.id"), nullable=False)
    tgl_masuk: Mapped[date] = mapped_column(Date, nullable=False)
    tgl_kedaluwarsa: Mapped[date] = mapped_column(Date, nullable=False)
    jumlah_awal: Mapped[int] = mapped_column(Integer, nullable=False)
    jumlah_sisa: Mapped[int] = mapped_column(Integer, nullable=False)
    hpp_satuan: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="aktif")

    produk: Mapped["Produk"] = relationship()

    __table_args__ = (
        CheckConstraint(_in("status", STATUS_BATCH), name="ck_batch_status"),
        CheckConstraint("jumlah_sisa >= 0", name="ck_batch_sisa_tidak_negatif"),
        # Jalur FEFO: batch aktif suatu produk diurutkan dari kedaluwarsa terdekat.
        Index("ix_batch_fefo", "produk_id", "status", "tgl_kedaluwarsa"),
        Index("ix_batch_kedaluwarsa", "tgl_kedaluwarsa"),
    )


class TransaksiPenjualan(Base):
    __tablename__ = "transaksi_penjualan"
    id: Mapped[int] = _pk()
    tanggal: Mapped[date] = mapped_column(Date, nullable=False)
    total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    catatan: Mapped[str | None] = mapped_column(Text)

    detail: Mapped[list["DetailPenjualan"]] = relationship(back_populates="transaksi")

    __table_args__ = (Index("ix_transaksi_tanggal", "tanggal"),)


class DetailPenjualan(Base):
    """Satu baris per BATCH yang tersentuh (penjualan boleh memecah ke beberapa batch)."""
    __tablename__ = "detail_penjualan"
    id: Mapped[int] = _pk()
    transaksi_id: Mapped[int] = mapped_column(ForeignKey("transaksi_penjualan.id"), nullable=False)
    produk_id: Mapped[int] = mapped_column(ForeignKey("produk.id"), nullable=False)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch_stok.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    harga_satuan: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hpp_satuan: Mapped[int] = mapped_column(BigInteger, nullable=False)

    transaksi: Mapped["TransaksiPenjualan"] = relationship(back_populates="detail")

    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_detail_qty_positif"),
        Index("ix_detail_transaksi", "transaksi_id"),
        Index("ix_detail_produk", "produk_id"),
        Index("ix_detail_batch", "batch_id"),
    )


class MutasiStok(Base):
    __tablename__ = "mutasi_stok"
    id: Mapped[int] = _pk()
    tanggal: Mapped[date] = mapped_column(Date, nullable=False)
    produk_id: Mapped[int] = mapped_column(ForeignKey("produk.id"), nullable=False)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batch_stok.id"))
    jenis: Mapped[str] = mapped_column(String(12), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)  # BERTANDA, lihat docstring modul
    keterangan: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_in("jenis", JENIS_MUTASI), name="ck_mutasi_jenis"),
        Index("ix_mutasi_tanggal", "tanggal"),
        Index("ix_mutasi_produk", "produk_id"),
        Index("ix_mutasi_batch", "batch_id"),
    )


class StockOpname(Base):
    __tablename__ = "stock_opname"
    id: Mapped[int] = _pk()
    tanggal: Mapped[date] = mapped_column(Date, nullable=False)
    produk_id: Mapped[int] = mapped_column(ForeignKey("produk.id"), nullable=False)
    stok_sistem: Mapped[int] = mapped_column(Integer, nullable=False)
    stok_fisik: Mapped[int] = mapped_column(Integer, nullable=False)
    selisih: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("ix_opname_produk_tanggal", "produk_id", "tanggal"),)


class BiayaOperasional(Base):
    __tablename__ = "biaya_operasional"
    id: Mapped[int] = _pk()
    tanggal: Mapped[date] = mapped_column(Date, nullable=False)
    kategori_biaya: Mapped[str] = mapped_column(String(100), nullable=False)
    jumlah: Mapped[int] = mapped_column(BigInteger, nullable=False)
    keterangan: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_biaya_tanggal", "tanggal"),)


class Writeoff(Base):
    __tablename__ = "writeoff"
    id: Mapped[int] = _pk()
    tanggal: Mapped[date] = mapped_column(Date, nullable=False)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch_stok.id"), nullable=False)
    produk_id: Mapped[int] = mapped_column(ForeignKey("produk.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    hpp_satuan: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_rugi: Mapped[int] = mapped_column(BigInteger, nullable=False)  # qty x hpp_satuan

    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_writeoff_qty_positif"),
        Index("ix_writeoff_tanggal", "tanggal"),
        Index("ix_writeoff_batch", "batch_id"),
    )


# --------------------------------------------------------------------------
# ML dan analitik (diisi fungsi milik Wulan)
# --------------------------------------------------------------------------
class HasilPrediksi(Base):
    __tablename__ = "hasil_prediksi"
    id: Mapped[int] = _pk()
    produk_id: Mapped[int] = mapped_column(ForeignKey("produk.id"), nullable=False)
    tanggal_target: Mapped[date] = mapped_column(Date, nullable=False)
    qty_prediksi: Mapped[float] = mapped_column(Float, nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    dibuat_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    __table_args__ = (Index("ix_prediksi_produk_target", "produk_id", "tanggal_target"),)


class EventMusiman(Base):
    __tablename__ = "event_musiman"
    id: Mapped[int] = _pk()
    nama: Mapped[str] = mapped_column(String(150), nullable=False)
    tgl_mulai: Mapped[date] = mapped_column(Date, nullable=False)
    tgl_selesai: Mapped[date] = mapped_column(Date, nullable=False)
    sumber: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")

    __table_args__ = (
        CheckConstraint(_in("sumber", SUMBER_EVENT), name="ck_event_sumber"),
        CheckConstraint("tgl_selesai >= tgl_mulai", name="ck_event_tanggal"),
    )


class IndeksMusim(Base):
    __tablename__ = "indeks_musim"
    id: Mapped[int] = _pk()
    produk_id: Mapped[int] = mapped_column(ForeignKey("produk.id"), nullable=False)
    bulan: Mapped[int] = mapped_column(Integer, nullable=False)
    indeks: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        CheckConstraint("bulan BETWEEN 1 AND 12", name="ck_indeks_bulan"),
        UniqueConstraint("produk_id", "bulan", name="uq_indeks_produk_bulan"),
    )


class Notifikasi(Base):
    __tablename__ = "notifikasi"
    id: Mapped[int] = _pk()
    jenis: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False, default="info")
    judul: Mapped[str] = mapped_column(String(200), nullable=False)
    pesan: Mapped[str | None] = mapped_column(Text)
    dibaca: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dibuat_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    # Rujukan longgar (tanpa FK) karena bisa menunjuk ke tabel mana pun.
    ref_tabel: Mapped[str | None] = mapped_column(String(50))
    ref_id: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint(_in("level", LEVEL_NOTIF), name="ck_notif_level"),
        Index("ix_notif_dibaca", "dibaca", "dibuat_pada"),
    )


class RekomendasiTindakan(Base):
    __tablename__ = "rekomendasi_tindakan"
    id: Mapped[int] = _pk()
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch_stok.id"), nullable=False)
    jenis: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    harga_diskon: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="menunggu")
    dibuat_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        CheckConstraint(_in("jenis", JENIS_REKOMENDASI), name="ck_rekom_jenis"),
        CheckConstraint(_in("status", STATUS_REKOMENDASI), name="ck_rekom_status"),
        Index("ix_rekom_batch", "batch_id"),
    )


class KoreksiPrediksi(Base):
    __tablename__ = "koreksi_prediksi"
    id: Mapped[int] = _pk()
    produk_id: Mapped[int] = mapped_column(ForeignKey("produk.id"), nullable=False)
    tanggal_target: Mapped[date] = mapped_column(Date, nullable=False)
    qty_koreksi: Mapped[float] = mapped_column(Float, nullable=False)
    alasan: Mapped[str | None] = mapped_column(Text)
    dibuat_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)


class EvaluasiModel(Base):
    __tablename__ = "evaluasi_model"
    id: Mapped[int] = _pk()
    produk_id: Mapped[int] = mapped_column(ForeignKey("produk.id"), nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    versi: Mapped[str | None] = mapped_column(String(30))
    mae: Mapped[float | None] = mapped_column(Float)
    rmse: Mapped[float | None] = mapped_column(Float)
    mape: Mapped[float | None] = mapped_column(Float)
    dievaluasi_pada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)


# --------------------------------------------------------------------------
# Pembelian, harga (pemilik: Naila)
# --------------------------------------------------------------------------
class PesananPembelian(Base):
    __tablename__ = "pesanan_pembelian"
    id: Mapped[int] = _pk()
    pemasok_id: Mapped[int] = mapped_column(ForeignKey("pemasok.id"), nullable=False)
    tanggal: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draf")
    jadwal_kirim: Mapped[date | None] = mapped_column(Date)
    catatan: Mapped[str | None] = mapped_column(Text)

    detail: Mapped[list["DetailPesanan"]] = relationship(back_populates="pesanan")

    __table_args__ = (
        CheckConstraint(_in("status", STATUS_PESANAN), name="ck_pesanan_status"),
        Index("ix_pesanan_status", "status"),
        Index("ix_pesanan_pemasok", "pemasok_id"),
    )


class DetailPesanan(Base):
    __tablename__ = "detail_pesanan"
    id: Mapped[int] = _pk()
    pesanan_id: Mapped[int] = mapped_column(ForeignKey("pesanan_pembelian.id"), nullable=False)
    produk_id: Mapped[int] = mapped_column(ForeignKey("produk.id"), nullable=False)
    qty_rekomendasi: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_final: Mapped[int] = mapped_column(Integer, nullable=False)
    harga_beli: Mapped[int] = mapped_column(BigInteger, nullable=False)

    pesanan: Mapped["PesananPembelian"] = relationship(back_populates="detail")

    __table_args__ = (
        Index("ix_detailpesanan_pesanan", "pesanan_id"),
        Index("ix_detailpesanan_produk", "produk_id"),
    )


class HargaJual(Base):
    """Riwayat harga jual. Harga yang berlaku sekarang juga disalin ke produk.harga_jual."""
    __tablename__ = "harga_jual"
    id: Mapped[int] = _pk()
    produk_id: Mapped[int] = mapped_column(ForeignKey("produk.id"), nullable=False)
    harga: Mapped[int] = mapped_column(BigInteger, nullable=False)
    berlaku_mulai: Mapped[date] = mapped_column(Date, nullable=False)
    sumber: Mapped[str] = mapped_column(String(12), nullable=False, default="manual")

    __table_args__ = (
        CheckConstraint(_in("sumber", SUMBER_HARGA), name="ck_hargajual_sumber"),
        Index("ix_hargajual_produk_mulai", "produk_id", "berlaku_mulai"),
    )


class HargaPesaing(Base):
    __tablename__ = "harga_pesaing"
    id: Mapped[int] = _pk()
    produk_id: Mapped[int] = mapped_column(ForeignKey("produk.id"), nullable=False)
    nama_pesaing: Mapped[str] = mapped_column(String(150), nullable=False)
    harga: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tanggal: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (Index("ix_hargapesaing_produk_tanggal", "produk_id", "tanggal"),)


# Urutan aman untuk INSERT (induk sebelum anak). Dipakai skrip pemuat data.
URUTAN_TABEL = [
    "users", "kategori", "pemasok", "produk", "batch_stok",
    "transaksi_penjualan", "detail_penjualan", "mutasi_stok", "stock_opname",
    "biaya_operasional", "writeoff", "hasil_prediksi", "event_musiman",
    "indeks_musim", "notifikasi", "rekomendasi_tindakan", "pesanan_pembelian",
    "detail_pesanan", "harga_jual", "harga_pesaing", "koreksi_prediksi",
    "evaluasi_model",
]
