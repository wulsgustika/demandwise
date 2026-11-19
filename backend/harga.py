"""backend/harga.py - rekomendasi harga jual (pemilik: Naila). KONTRAK 3.6 dan bagian 4.

Aturan (KONTRAK bagian 4):
  harga dasar = HPP + margin target, disesuaikan indeks musim dan harga pesaing,
  TIDAK BOLEH di bawah margin minimum.

Definisi margin di sini: margin = (harga - HPP) / harga   (margin atas harga jual).
Jadi harga untuk margin m adalah HPP / (1 - m).

Konstanta di bawah adalah USULAN. Ubah di sini saja, rumus tidak perlu disentuh.

Langkah 1: rumus murni (hitung_harga_rekomendasi).
Langkah 2: get_rekomendasi_harga, tabel KONTRAK 3.6 dari data database.
Langkah 3: setujui_harga dan ubah_harga_manual (menulis riwayat di harga_jual).
"""
import math
from datetime import date

import pandas as pd
from sqlalchemy import select

from .models import BatchStok, HargaJual, HargaPesaing, IndeksMusim, Produk

MARGIN_MINIMUM = 0.15      # usulan KONTRAK bagian 4, diputuskan Naila (Sab 14)
MARGIN_TARGET = 0.25       # USULAN SEMENTARA, belum ada di KONTRAK
FAKTOR_MUSIM = 0.25        # seberapa kuat indeks musim menggeser harga
BATAS_MUSIM = (0.95, 1.10)  # geseran musim dibatasi -5% sampai +10%
BATAS_ATAS_PESAING = 1.05  # harga tidak melebihi rata-rata pesaing x 1,05
PEMBULATAN = 500           # harga dibulatkan KE ATAS ke kelipatan ini


def harga_untuk_margin(hpp: float, margin: float) -> float:
    """Harga jual agar margin (atas harga jual) tepat sebesar `margin`."""
    return hpp / (1 - margin)


def hitung_margin_persen(harga: float, hpp: float) -> float:
    """Margin dalam persen (atas harga jual). Harga 0 atau kurang -> 0."""
    if harga <= 0:
        return 0.0
    return round((harga - hpp) / harga * 100, 1)


def _bulatkan_ke_atas(harga: float) -> int:
    return int(math.ceil(harga / PEMBULATAN) * PEMBULATAN)


def hitung_harga_rekomendasi(hpp, indeks_musim=None, harga_pesaing_rata2=None) -> dict:
    """Hitung harga rekomendasi. Murni hitungan, tidak menyentuh database.

    Return {"harga": int, "alasan": str}. `hpp` harus > 0, kalau tidak ValueError.
    """
    if hpp is None or hpp <= 0:
        raise ValueError("HPP harus lebih dari 0")

    harga = harga_untuk_margin(hpp, MARGIN_TARGET)
    alasan = [f"HPP + margin target {MARGIN_TARGET:.0%}"]

    # 1) musim: indeks > 1 menaikkan harga, < 1 menurunkan (dibatasi)
    if indeks_musim is not None and indeks_musim > 0:
        faktor = 1 + (indeks_musim - 1) * FAKTOR_MUSIM
        faktor = min(max(faktor, BATAS_MUSIM[0]), BATAS_MUSIM[1])
        if abs(faktor - 1) > 1e-9:
            harga *= faktor
            arah = "naik" if faktor > 1 else "turun"
            alasan.append(f"indeks musim {indeks_musim:.2f}, harga {arah} {abs(faktor - 1):.1%}")

    # 2) pesaing: jangan terlalu jauh di atas rata-rata pesaing
    if harga_pesaing_rata2 is not None and harga_pesaing_rata2 > 0:
        batas = harga_pesaing_rata2 * BATAS_ATAS_PESAING
        if harga > batas:
            harga = batas
            alasan.append("dibatasi harga pesaing")

    # 3) margin minimum selalu menang
    lantai = harga_untuk_margin(hpp, MARGIN_MINIMUM)
    if harga < lantai:
        harga = lantai
        alasan.append(f"dinaikkan ke margin minimum {MARGIN_MINIMUM:.0%}")

    # pembulatan ke atas tidak pernah menurunkan harga di bawah lantai
    return {"harga": _bulatkan_ke_atas(harga), "alasan": "; ".join(alasan)}


# ---------------------------------------------------------------------------
# Langkah 2: tabel rekomendasi harga (KONTRAK 3.6)
# ---------------------------------------------------------------------------
KOLOM_HARGA = ["produk_id", "nama_produk", "hpp", "harga_saat_ini", "harga_pesaing_rata2",
               "indeks_musim", "harga_rekomendasi", "margin_persen", "alasan"]

# Dipakai kalau Wulan belum mengisi tabel indeks_musim untuk produk dan bulan itu.
INDEKS_MUSIM_NETRAL = 1.0


def get_hpp_per_produk(s) -> dict:
    """{produk_id: HPP}. Utama: produk.harga_beli_terakhir.
    Kalau kosong: hpp_satuan batch aktif yang paling baru masuk. Tidak ada -> tidak masuk dict."""
    hpp = {}
    for pid, harga in s.execute(select(Produk.id, Produk.harga_beli_terakhir)):
        if harga and harga > 0:
            hpp[pid] = harga
    batch = s.execute(
        select(BatchStok.produk_id, BatchStok.hpp_satuan)
        .where(BatchStok.status == "aktif")
        .order_by(BatchStok.tgl_masuk, BatchStok.id)).all()
    cadangan = {pid: h for pid, h in batch if h and h > 0}   # yang terakhir menang
    for pid, h in cadangan.items():
        hpp.setdefault(pid, h)
    return hpp


def get_harga_pesaing_rata2(s, tanggal) -> dict:
    """{produk_id: rata-rata}. Dipakai harga TERBARU tiap pesaing (sampai `tanggal`),
    supaya harga lama pesaing tidak ikut menarik rata-rata."""
    terbaru = {}
    rows = s.execute(
        select(HargaPesaing.produk_id, HargaPesaing.nama_pesaing, HargaPesaing.harga)
        .where(HargaPesaing.tanggal <= tanggal)
        .order_by(HargaPesaing.tanggal, HargaPesaing.id)).all()
    for pid, pesaing, harga in rows:
        terbaru[(pid, pesaing)] = harga                      # yang terakhir menang
    kumpul = {}
    for (pid, _), harga in terbaru.items():
        kumpul.setdefault(pid, []).append(harga)
    return {pid: sum(v) / len(v) for pid, v in kumpul.items()}


def get_indeks_musim_bulan(s, bulan: int) -> dict:
    """{produk_id: indeks} untuk bulan itu, dari tabel milik Wulan (bisa kosong)."""
    return {pid: idx for pid, idx in s.execute(
        select(IndeksMusim.produk_id, IndeksMusim.indeks).where(IndeksMusim.bulan == bulan))}


def hitung_rekomendasi_harga(s, tanggal: date) -> pd.DataFrame:
    """Satu baris per produk aktif. Produk tanpa HPP tetap muncul, harga_rekomendasi kosong."""
    hpp = get_hpp_per_produk(s)
    pesaing = get_harga_pesaing_rata2(s, tanggal)
    musim = get_indeks_musim_bulan(s, tanggal.month)

    produk = s.execute(
        select(Produk.id, Produk.nama, Produk.harga_jual)
        .where(Produk.aktif.is_(True)).order_by(Produk.nama)).all()

    baris = []
    for pid, nama, harga_jual in produk:
        h = hpp.get(pid)
        pes = pesaing.get(pid)
        idx = musim.get(pid)
        rekom, margin, alasan = None, None, "HPP belum ada, harga tidak bisa dihitung"
        if h:
            hasil = hitung_harga_rekomendasi(h, idx, pes)
            rekom, alasan = hasil["harga"], hasil["alasan"]
            margin = hitung_margin_persen(rekom, h)
            if idx is None:
                alasan += "; indeks musim belum ada (dianggap netral)"
        baris.append({
            "produk_id": pid,
            "nama_produk": nama,
            "hpp": h,
            "harga_saat_ini": harga_jual,
            "harga_pesaing_rata2": None if pes is None else round(pes),
            "indeks_musim": INDEKS_MUSIM_NETRAL if idx is None else round(idx, 2),
            "harga_rekomendasi": rekom,
            "margin_persen": margin,
            "alasan": alasan,
        })
    return pd.DataFrame(baris, columns=KOLOM_HARGA)


def get_rekomendasi_harga() -> pd.DataFrame:
    """Fungsi KONTRAK 2.2 (dipakai Dhea). Sesi sendiri, tanggal = hari ini.
    Error -> tabel kosong dengan kolom yang sama (KONTRAK 6)."""
    from .db import get_session
    try:
        with get_session() as s:
            return hitung_rekomendasi_harga(s, date.today())
    except Exception:
        return pd.DataFrame(columns=KOLOM_HARGA)


# ---------------------------------------------------------------------------
# Langkah 3: setujui harga rekomendasi dan ubah harga manual
# ---------------------------------------------------------------------------
# Keduanya menambah SATU baris riwayat di harga_jual (sumber 'rekomendasi'/'manual')
# dan menyalin harganya ke produk.harga_jual (harga yang dipakai kasir).
def _terapkan_harga(s, produk, harga: int, tanggal: date, sumber: str) -> None:
    s.add(HargaJual(produk_id=produk.id, harga=harga, berlaku_mulai=tanggal, sumber=sumber))
    produk.harga_jual = harga


def setujui_harga_di(s, produk_id: int, tanggal: date) -> dict:
    """Terapkan harga rekomendasi terbaru untuk satu produk. Belum commit."""
    produk = s.get(Produk, produk_id)
    if produk is None:
        return {"ok": False, "pesan": "Produk tidak ditemukan", "data": None}
    if not produk.aktif:
        return {"ok": False, "pesan": "Produk tidak aktif", "data": None}

    df = hitung_rekomendasi_harga(s, tanggal)
    baris = df[df["produk_id"] == produk_id].iloc[0]
    if pd.isna(baris["harga_rekomendasi"]):
        return {"ok": False, "pesan": "HPP produk belum ada, harga rekomendasi tidak bisa dihitung",
                "data": None}

    harga = int(baris["harga_rekomendasi"])
    lama = produk.harga_jual
    if lama == harga:
        return {"ok": True, "pesan": "Harga sudah sama dengan rekomendasi, tidak ada perubahan",
                "data": {"produk_id": produk_id, "harga_lama": lama, "harga_baru": harga,
                         "diubah": False}}
    _terapkan_harga(s, produk, harga, tanggal, "rekomendasi")
    return {"ok": True, "pesan": "Harga rekomendasi diterapkan",
            "data": {"produk_id": produk_id, "harga_lama": lama, "harga_baru": harga,
                     "diubah": True}}


def ubah_harga_manual_di(s, produk_id: int, harga, tanggal: date) -> dict:
    """Pasang harga yang diketik pemilik. Ditolak kalau margin di bawah minimum. Belum commit."""
    if isinstance(harga, bool) or not isinstance(harga, int) or harga <= 0:
        return {"ok": False, "pesan": "Harga harus berupa bilangan bulat lebih dari 0", "data": None}
    produk = s.get(Produk, produk_id)
    if produk is None:
        return {"ok": False, "pesan": "Produk tidak ditemukan", "data": None}
    if not produk.aktif:
        return {"ok": False, "pesan": "Produk tidak aktif", "data": None}

    hpp = get_hpp_per_produk(s).get(produk_id)
    if not hpp:
        return {"ok": False, "pesan": "HPP produk belum ada, margin tidak bisa dicek", "data": None}

    harga_min = _bulatkan_ke_atas(harga_untuk_margin(hpp, MARGIN_MINIMUM))
    if harga < harga_untuk_margin(hpp, MARGIN_MINIMUM):
        return {"ok": False,
                "pesan": (f"Harga {harga:,} di bawah margin minimum {MARGIN_MINIMUM:.0%} "
                          f"(HPP {hpp:,}). Harga minimal sekitar {harga_min:,}").replace(",", "."),
                "data": None}

    lama = produk.harga_jual
    _terapkan_harga(s, produk, harga, tanggal, "manual")
    return {"ok": True, "pesan": "Harga manual disimpan",
            "data": {"produk_id": produk_id, "harga_lama": lama, "harga_baru": harga,
                     "margin_persen": hitung_margin_persen(harga, hpp)}}


def setujui_harga(produk_id: int) -> dict:
    """Fungsi KONTRAK 2.2 (dipakai Dhea). Error tidak dilempar ke layar (KONTRAK 6)."""
    from .pembelian import _jalankan
    return _jalankan(setujui_harga_di, produk_id, date.today())


def ubah_harga_manual(produk_id: int, harga: int) -> dict:
    """Fungsi KONTRAK 2.2 (dipakai Dhea). Error tidak dilempar ke layar (KONTRAK 6)."""
    from .pembelian import _jalankan
    return _jalankan(ubah_harga_manual_di, produk_id, harga, date.today())
