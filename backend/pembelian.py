"""backend/pembelian.py - Alur pembelian DemandWise (pemilik: Naila).

Langkah 1: rumus jumlah beli (murni hitungan).
Langkah 2: baca stok dan pesanan berjalan dari database.
Langkah 3: prediksi dan safety stock SEMENTARA (palsu); dipakai sebagai cadangan
          kalau data Wulan (get_stok_status) belum ada atau tidak lengkap.
Langkah 4: get_rekomendasi_pembelian (menggabungkan langkah 1-3).
Langkah 5: buat_draf_pesanan (membuat pesanan berstatus 'draf' per pemasok).
Langkah 6a: setujui_pesanan dan revisi_pesanan.
Langkah 6b: simpan_jadwal_kirim (notifikasi lewat backend/notifikasi.py).
Langkah 7: get_teks_pesanan_wa dan terima_pesanan (membuat batch baru).
Rumus mengikuti KONTRAK.md bagian 4:
  qty_hitung      = prediksi_lead_time + safety_stock - stok - pesanan_berjalan
  batas           = prediksi_harian x sisa_umur_simpan
  qty_rekomendasi = min(qty_hitung, batas), minimal 0
"""
import math
from datetime import date, timedelta

import pandas as pd

from sqlalchemy import func, select

from .models import (User, BatchStok, DetailPenjualan, DetailPesanan, Notifikasi, Pemasok,
                     PesananPembelian, Produk, TransaksiPenjualan)


def hitung_qty_beli(stok, prediksi_lead_time, safety_stock, pesanan_berjalan,
                    prediksi_harian, sisa_umur_simpan):
    """Hitung jumlah beli untuk satu produk.

    Return dict: qty_hitung, batas_masa_simpan, qty_rekomendasi.
    Semua dibulatkan ke atas ke bilangan bulat (barang tidak dibeli pecahan).
    sisa_umur_simpan None = umur simpan tidak diketahui -> tidak ada batas
    (batas_masa_simpan None, qty_rekomendasi = qty_hitung).
    """
    qty_hitung = prediksi_lead_time + safety_stock - stok - pesanan_berjalan
    if sisa_umur_simpan is None:
        return {
            "qty_hitung": max(0, math.ceil(qty_hitung)),
            "batas_masa_simpan": None,
            "qty_rekomendasi": max(0, math.ceil(qty_hitung)),
        }
    batas = prediksi_harian * sisa_umur_simpan
    qty_rek = max(0, min(qty_hitung, batas))
    return {
        "qty_hitung": max(0, math.ceil(qty_hitung)),
        "batas_masa_simpan": max(0, math.ceil(batas)),
        "qty_rekomendasi": math.ceil(qty_rek),
    }


# ---------------------------------------------------------------------------
# Langkah 2: membaca stok dan pesanan berjalan dari database
# Fungsi menerima `s` (session) supaya mudah dites. Pemakai: with get_session() as s
# ---------------------------------------------------------------------------
# Pesanan yang sudah dipesan tapi barangnya belum masuk stok.
# 'draf' belum dipesan; 'diterima' sudah jadi batch; 'dibatalkan' tidak datang.
STATUS_PESANAN_BERJALAN = ("dipesan", "dikirim")


def get_stok_per_produk(s) -> dict:
    """Total stok sekarang per produk = jumlah_sisa semua batch berstatus 'aktif'.

    Return {produk_id: stok}. Produk tanpa batch aktif tidak muncul; pemakai
    memakai .get(produk_id, 0).
    """
    baris = s.execute(
        select(BatchStok.produk_id, func.sum(BatchStok.jumlah_sisa))
        .where(BatchStok.status == "aktif")
        .group_by(BatchStok.produk_id)
    ).all()
    return {pid: int(total) for pid, total in baris}


def get_pesanan_berjalan(s) -> dict:
    """Total qty_final per produk dari pesanan berstatus dipesan/dikirim.

    Return {produk_id: qty}. Produk tanpa pesanan berjalan tidak muncul.
    """
    baris = s.execute(
        select(DetailPesanan.produk_id, func.sum(DetailPesanan.qty_final))
        .join(PesananPembelian, PesananPembelian.id == DetailPesanan.pesanan_id)
        .where(PesananPembelian.status.in_(STATUS_PESANAN_BERJALAN))
        .group_by(DetailPesanan.produk_id)
    ).all()
    return {pid: int(total) for pid, total in baris}


# ---------------------------------------------------------------------------
# Langkah 3: prediksi dan safety stock SEMENTARA (PALSU)
# ---------------------------------------------------------------------------
# Rumus prediksi dan safety stock milik Wulan (KONTRAK bagian 4). Fungsi di bawah
# hanya pengganti sampai datanya tersambung. Nanti cukup ganti ISI fungsi ini
# (jadi baca dari hasil_prediksi / get_stok_status Wulan); pemanggilnya tidak berubah.
JENDELA_RATA_RATA_HARI = 30      # prediksi_harian palsu = rata-rata penjualan 30 hari terakhir
FAKTOR_SAFETY_STOCK_PALSU = 0.2  # safety stock palsu = 20% dari prediksi_lead_time


def get_prediksi_sementara(s, tanggal) -> dict:
    """PALSU, ganti nanti dengan data Wulan.

    Return {produk_id: {"lead_time_hari", "prediksi_harian",
                        "prediksi_lead_time", "safety_stock"}} untuk produk aktif.
    lead_time_hari: dari produk; kalau kosong, dari pemasoknya; kalau masih kosong, 1.
    """
    awal = tanggal - timedelta(days=JENDELA_RATA_RATA_HARI)
    terjual = dict(s.execute(
        select(DetailPenjualan.produk_id, func.sum(DetailPenjualan.qty))
        .join(TransaksiPenjualan, TransaksiPenjualan.id == DetailPenjualan.transaksi_id)
        .where(TransaksiPenjualan.tanggal > awal, TransaksiPenjualan.tanggal <= tanggal)
        .group_by(DetailPenjualan.produk_id)
    ).all())

    produk = s.execute(
        select(Produk.id, Produk.lead_time_hari, Pemasok.lead_time_hari)
        .outerjoin(Pemasok, Pemasok.id == Produk.pemasok_id)
        .where(Produk.aktif.is_(True))
    ).all()

    hasil = {}
    for pid, lt_produk, lt_pemasok in produk:
        lead_time = lt_produk if lt_produk is not None else (lt_pemasok if lt_pemasok is not None else 1)
        harian = float(terjual.get(pid, 0)) / JENDELA_RATA_RATA_HARI
        prediksi_lt = harian * lead_time
        hasil[pid] = {
            "lead_time_hari": lead_time,
            "prediksi_harian": harian,
            "prediksi_lead_time": prediksi_lt,
            "safety_stock": prediksi_lt * FAKTOR_SAFETY_STOCK_PALSU,
        }
    return hasil


# ---------------------------------------------------------------------------
# Sambungan Wulan: prediksi dan safety stock asli dari get_stok_status()
# ---------------------------------------------------------------------------
def ambil_stok_status_wulan():
    """DataFrame get_stok_status() milik Wulan, atau None kalau tidak tersedia.

    None kalau modul backend.analitik belum ada, gagal dijalankan, atau hasilnya kosong.
    Pemanggil lalu memakai prediksi sementara (palsu) sebagai cadangan.
    """
    try:
        from .analitik import get_stok_status
        df = get_stok_status()
    except Exception:
        return None
    if df is None or df.empty:
        return None
    return df


def gabung_prediksi_wulan(s, palsu: dict, stok_status) -> dict:
    """Timpa prediksi_lead_time dan safety_stock dengan milik Wulan.

    palsu       : hasil get_prediksi_sementara (dasar dan cadangan).
    stok_status : DataFrame get_stok_status() Wulan, atau None (hasil = palsu).

    prediksi_harian (dipakai untuk batas masa simpan) diturunkan dari data Wulan:
    prediksi_demand_lead_time / lead time yang Wulan pakai (produk.lead_time_hari,
    kosong dianggap 1, sama dengan aturannya). Produk yang tidak ada di data Wulan,
    atau angkanya kosong, tetap memakai nilai palsu.
    """
    hasil = {pid: dict(v) for pid, v in palsu.items()}
    if stok_status is None:
        return hasil
    lt_wulan = {pid: max(1, int(lt)) if lt is not None else 1 for pid, lt in s.execute(
        select(Produk.id, Produk.lead_time_hari)).all()}
    for r in stok_status.itertuples(index=False):
        pid = int(r.produk_id)
        if pid not in hasil:
            continue
        dem = pd.to_numeric(r.prediksi_demand_lead_time, errors="coerce")
        ss = pd.to_numeric(r.safety_stock, errors="coerce")
        if pd.isna(dem) or pd.isna(ss):
            continue
        hasil[pid]["prediksi_lead_time"] = float(dem)
        hasil[pid]["safety_stock"] = float(ss)
        hasil[pid]["prediksi_harian"] = float(dem) / lt_wulan.get(pid, 1)
    return hasil


# ---------------------------------------------------------------------------
# Langkah 4: tabel rekomendasi pembelian (KONTRAK 3.5)
# ---------------------------------------------------------------------------
KOLOM_REKOMENDASI = ["produk_id", "nama_produk", "pemasok", "stok_saat_ini",
                     "prediksi_lead_time", "safety_stock", "pesanan_berjalan",
                     "qty_hitung", "batas_masa_simpan", "qty_rekomendasi", "ditunda"]


def hitung_rekomendasi_pembelian(s, tanggal, stok_status=None) -> pd.DataFrame:
    """Satu baris per produk aktif. Dipisah dari get_rekomendasi_pembelian supaya mudah dites.

    stok_status: DataFrame get_stok_status() Wulan. Kosong (None) berarti memakai
    prediksi sementara (palsu); isi dari fungsi publik lewat ambil_stok_status_wulan().

    sisa_umur_simpan = umur_simpan_hari - lead_time_hari (barang baru tiba setelah
    lead time). Umur simpan kosong -> tanpa batas masa simpan.
    """
    stok = get_stok_per_produk(s)
    berjalan = get_pesanan_berjalan(s)
    prediksi = gabung_prediksi_wulan(s, get_prediksi_sementara(s, tanggal), stok_status)

    produk = s.execute(
        select(Produk.id, Produk.nama, Produk.umur_simpan_hari, Produk.tunda_pesan, Pemasok.nama)
        .outerjoin(Pemasok, Pemasok.id == Produk.pemasok_id)
        .where(Produk.aktif.is_(True))
        .order_by(Produk.nama)
    ).all()

    baris = []
    for pid, nama, umur, tunda, nama_pemasok in produk:
        p = prediksi[pid]
        sisa_umur = None if umur is None else max(0, umur - p["lead_time_hari"])
        hitung = hitung_qty_beli(
            stok=stok.get(pid, 0),
            prediksi_lead_time=p["prediksi_lead_time"],
            safety_stock=p["safety_stock"],
            pesanan_berjalan=berjalan.get(pid, 0),
            prediksi_harian=p["prediksi_harian"],
            sisa_umur_simpan=sisa_umur,
        )
        baris.append({
            "produk_id": pid,
            "nama_produk": nama,
            "pemasok": nama_pemasok or "-",
            "stok_saat_ini": stok.get(pid, 0),
            "prediksi_lead_time": round(p["prediksi_lead_time"], 2),
            "safety_stock": round(p["safety_stock"], 2),
            "pesanan_berjalan": berjalan.get(pid, 0),
            "qty_hitung": hitung["qty_hitung"],
            "batas_masa_simpan": hitung["batas_masa_simpan"],
            "qty_rekomendasi": hitung["qty_rekomendasi"],
            "ditunda": bool(tunda),
        })
    return pd.DataFrame(baris, columns=KOLOM_REKOMENDASI)


def get_rekomendasi_pembelian() -> pd.DataFrame:
    """Fungsi KONTRAK 2.2 (dipakai Dhea). Membuka sesi sendiri, tanggal = hari ini."""
    from .db import get_session
    with get_session() as s:
        return hitung_rekomendasi_pembelian(s, date.today(), ambil_stok_status_wulan())


# ---------------------------------------------------------------------------
# Langkah 5: buat draf pesanan (satu pesanan 'draf' per pemasok)
# ---------------------------------------------------------------------------
def buat_draf_dari_rekomendasi(s, tanggal, stok_status=None) -> dict:
    """Isi tabel pesanan_pembelian + detail_pesanan dari rekomendasi. Tidak commit.

    Dilewati: produk qty_rekomendasi 0, produk ditunda, produk tanpa pemasok,
    dan pemasok yang sudah punya draf (supaya klik dua kali tidak menggandakan).
    Return {"pesanan_id": [...], "dilewati": {...}}.
    """
    rek = hitung_rekomendasi_pembelian(s, tanggal, stok_status)
    info = {pid: (pemasok_id, harga) for pid, pemasok_id, harga in s.execute(
        select(Produk.id, Produk.pemasok_id, Produk.harga_beli_terakhir)).all()}
    pemasok_sudah_draf = set(s.scalars(
        select(PesananPembelian.pemasok_id).where(PesananPembelian.status == "draf")))

    dilewati = {"ditunda": [], "tanpa_pemasok": [], "sudah_ada_draf": []}
    per_pemasok = {}   # pemasok_id -> [(produk_id, qty, harga_beli)]
    for r in rek.itertuples(index=False):
        if r.qty_rekomendasi <= 0:
            continue
        pemasok_id, harga = info[r.produk_id]
        if r.ditunda:
            dilewati["ditunda"].append(r.nama_produk)
        elif pemasok_id is None:
            dilewati["tanpa_pemasok"].append(r.nama_produk)
        elif pemasok_id in pemasok_sudah_draf:
            if r.pemasok not in dilewati["sudah_ada_draf"]:
                dilewati["sudah_ada_draf"].append(r.pemasok)
        else:
            per_pemasok.setdefault(pemasok_id, []).append(
                (r.produk_id, int(r.qty_rekomendasi), int(harga or 0)))

    pesanan_id = []
    for pemasok_id, item in per_pemasok.items():
        p = PesananPembelian(pemasok_id=pemasok_id, tanggal=tanggal, status="draf")
        s.add(p)
        s.flush()
        for produk_id, qty, harga in item:
            s.add(DetailPesanan(pesanan_id=p.id, produk_id=produk_id, qty_rekomendasi=qty,
                                qty_final=qty, harga_beli=harga))
        pesanan_id.append(p.id)
    return {"pesanan_id": pesanan_id, "dilewati": dilewati}


def buat_draf_pesanan() -> dict:
    """Fungsi KONTRAK 2.2 (dipakai Dhea). Return {"ok", "pesan", "data"}."""
    from .db import get_session
    try:
        with get_session() as s:
            hasil = buat_draf_dari_rekomendasi(s, date.today(), ambil_stok_status_wulan())
            s.commit()
    except Exception as e:  # KONTRAK 6: backend tidak melempar error ke layar
        return {"ok": False, "pesan": f"Gagal membuat draf pesanan: {e}", "data": None}
    n = len(hasil["pesanan_id"])
    pesan = (f"{n} draf pesanan dibuat" if n else "Tidak ada draf baru yang perlu dibuat")
    return {"ok": True, "pesan": pesan, "data": hasil}


# ---------------------------------------------------------------------------
# Langkah 6a: setujui dan revisi pesanan
# ---------------------------------------------------------------------------
def setujui_pesanan_di(s, pesanan_id: int) -> dict:
    """Ubah status 'draf' -> 'dipesan'. Return {"ok", "pesan", "data"}. Belum commit."""
    p = s.get(PesananPembelian, pesanan_id)
    if p is None:
        return {"ok": False, "pesan": "Pesanan tidak ditemukan", "data": None}
    if p.status != "draf":
        return {"ok": False, "pesan": f"Pesanan berstatus '{p.status}', hanya draf yang bisa disetujui",
                "data": None}
    total_qty = s.scalar(select(func.coalesce(func.sum(DetailPesanan.qty_final), 0))
                         .where(DetailPesanan.pesanan_id == pesanan_id))
    if not total_qty:
        return {"ok": False, "pesan": "Pesanan kosong, tidak ada barang yang dipesan", "data": None}
    p.status = "dipesan"
    return {"ok": True, "pesan": "Pesanan disetujui",
            "data": {"pesanan_id": pesanan_id, "status": p.status}}


def revisi_pesanan_di(s, pesanan_id: int, items: list) -> dict:
    """Ubah qty_final. items = [{"produk_id": 1, "qty_final": 20}, ...].

    Semua item dicek dulu. Kalau satu saja salah, tidak ada yang diubah.
    """
    p = s.get(PesananPembelian, pesanan_id)
    if p is None:
        return {"ok": False, "pesan": "Pesanan tidak ditemukan", "data": None}
    if p.status != "draf":
        return {"ok": False, "pesan": f"Pesanan berstatus '{p.status}', hanya draf yang bisa direvisi",
                "data": None}
    if not items:
        return {"ok": False, "pesan": "Tidak ada item yang direvisi", "data": None}

    baris = {d.produk_id: d for d in s.scalars(
        select(DetailPesanan).where(DetailPesanan.pesanan_id == pesanan_id))}
    perubahan = {}
    for it in items:
        pid, qty = it.get("produk_id"), it.get("qty_final")
        if pid not in baris:
            return {"ok": False, "pesan": f"Produk {pid} tidak ada di pesanan ini", "data": None}
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0:
            return {"ok": False, "pesan": f"Jumlah untuk produk {pid} harus bilangan bulat >= 0",
                    "data": None}
        perubahan[pid] = qty

    for pid, qty in perubahan.items():
        baris[pid].qty_final = qty
    return {"ok": True, "pesan": f"{len(perubahan)} item direvisi",
            "data": {"pesanan_id": pesanan_id, "diubah": perubahan}}


def _jalankan(fungsi, *args) -> dict:
    """Buka sesi, jalankan, commit kalau ok. Error tidak dilempar ke layar (KONTRAK 6)."""
    from .db import get_session
    try:
        with get_session() as s:
            hasil = fungsi(s, *args)
            if hasil["ok"]:
                s.commit()
            else:
                s.rollback()
            return hasil
    except Exception as e:
        return {"ok": False, "pesan": f"Gagal: {e}", "data": None}


def setujui_pesanan(pesanan_id: int) -> dict:
    """Fungsi KONTRAK 2.2 (dipakai Dhea)."""
    return _jalankan(setujui_pesanan_di, pesanan_id)


def revisi_pesanan(pesanan_id: int, items: list) -> dict:
    """Fungsi KONTRAK 2.2 (dipakai Dhea)."""
    return _jalankan(revisi_pesanan_di, pesanan_id, items)


# ---------------------------------------------------------------------------
# Langkah 6b: jadwal kirim
# ---------------------------------------------------------------------------
def _kirim_notif_pesanan_dikirim(s, pesanan, tanggal) -> None:
    """Notifikasi 'pesanan_dikirim' (KONTRAK bagian 5) lewat backend/notifikasi.py."""
    from .notifikasi import kirim_notifikasi_di
    pemasok = s.get(Pemasok, pesanan.pemasok_id)
    nama = pemasok.nama if pemasok else f"pemasok {pesanan.pemasok_id}"
    kirim_notifikasi_di(s, "pesanan_dikirim", "info",
                        f"Jadwal kirim pesanan #{pesanan.id} dicatat",
                        f"Pesanan dari {nama} dijadwalkan tiba {tanggal.isoformat()}.",
                        "pesanan_pembelian", pesanan.id)


def simpan_jadwal_kirim_di(s, pesanan_id: int, tanggal) -> dict:
    """Simpan jadwal kirim, status 'dipesan' -> 'dikirim', lalu kirim notifikasi."""
    if not isinstance(tanggal, date):
        return {"ok": False, "pesan": "Tanggal kirim tidak valid", "data": None}
    p = s.get(PesananPembelian, pesanan_id)
    if p is None:
        return {"ok": False, "pesan": "Pesanan tidak ditemukan", "data": None}
    if p.status != "dipesan":
        return {"ok": False, "pesan": f"Pesanan berstatus '{p.status}', jadwal hanya bisa diisi "
                                      "untuk pesanan yang sudah disetujui (dipesan)", "data": None}
    if tanggal < p.tanggal:
        return {"ok": False, "pesan": "Jadwal kirim tidak boleh sebelum tanggal pesanan", "data": None}
    p.jadwal_kirim = tanggal
    p.status = "dikirim"
    _kirim_notif_pesanan_dikirim(s, p, tanggal)
    return {"ok": True, "pesan": "Jadwal kirim disimpan",
            "data": {"pesanan_id": pesanan_id, "jadwal_kirim": tanggal.isoformat(),
                     "status": p.status}}


def simpan_jadwal_kirim(pesanan_id: int, tanggal) -> dict:
    """Fungsi KONTRAK 2.2 (dipakai Dhea). tanggal = objek date."""
    return _jalankan(simpan_jadwal_kirim_di, pesanan_id, tanggal)


# ---------------------------------------------------------------------------
# Langkah 7: teks WhatsApp dan terima pesanan
# ---------------------------------------------------------------------------
def get_teks_pesanan_wa_di(s, pesanan_id: int) -> str:
    """Teks siap salin untuk WhatsApp. Item dengan qty_final 0 tidak ditulis."""
    p = s.get(PesananPembelian, pesanan_id)
    if p is None:
        return "Pesanan tidak ditemukan"
    pemasok = s.get(Pemasok, p.pemasok_id)
    from .konteks import user_id_aktif
    uid = user_id_aktif()
    if uid is None:   # mode demo: perilaku lama (nama usaha akun pertama)
        usaha = s.scalar(select(User.nama_usaha).order_by(User.id)) or "toko kami"
    else:             # akun pengguna: nama usaha akunnya sendiri
        usaha = s.scalar(select(User.nama_usaha).where(User.id == uid)) or "toko kami"
    baris = s.execute(
        select(Produk.nama, Produk.satuan, DetailPesanan.qty_final)
        .join(Produk, Produk.id == DetailPesanan.produk_id)
        .where(DetailPesanan.pesanan_id == pesanan_id, DetailPesanan.qty_final > 0)
        .order_by(Produk.nama)).all()
    if not baris:
        return "Pesanan ini belum ada barang yang dipesan"
    daftar = "\n".join(f"{i}. {nama} - {qty} {satuan or ''}".rstrip()
                       for i, (nama, satuan, qty) in enumerate(baris, 1))
    return (f"Halo {pemasok.nama if pemasok else 'Bapak/Ibu'},\n"
            f"Kami dari {usaha} ingin memesan:\n\n{daftar}\n\n"
            "Mohon konfirmasi ketersediaan dan jadwal kirimnya. Terima kasih.")


def get_teks_pesanan_wa(pesanan_id: int) -> str:
    """Fungsi KONTRAK 2.2 (dipakai Dhea). Return str."""
    from .db import get_session
    try:
        with get_session() as s:
            return get_teks_pesanan_wa_di(s, pesanan_id)
    except Exception as e:
        return f"Gagal membuat teks pesanan: {e}"


def terima_pesanan_di(s, pesanan_id: int, tanggal=None) -> dict:
    """Pesanan 'dikirim' -> 'diterima'. Tiap item jadi batch baru lewat catat_barang_masuk.

    tgl_kedaluwarsa = tanggal terima + produk.umur_simpan_hari
    hpp_satuan      = detail_pesanan.harga_beli (juga mengisi produk.harga_beli_terakhir)
    Kalau gagal, pemanggil harus rollback (fungsi pembungkus sudah melakukannya).
    """
    from .stok import catat_barang_masuk_di
    tanggal = tanggal or date.today()
    p = s.get(PesananPembelian, pesanan_id)
    if p is None:
        return {"ok": False, "pesan": "Pesanan tidak ditemukan", "data": None}
    if p.status != "dikirim":
        return {"ok": False, "pesan": f"Pesanan berstatus '{p.status}', hanya pesanan yang sudah "
                                      "dikirim yang bisa diterima", "data": None}
    item = s.execute(select(DetailPesanan, Produk)
                     .join(Produk, Produk.id == DetailPesanan.produk_id)
                     .where(DetailPesanan.pesanan_id == pesanan_id,
                            DetailPesanan.qty_final > 0)).all()
    if not item:
        return {"ok": False, "pesan": "Pesanan kosong, tidak ada barang untuk diterima", "data": None}
    tanpa_umur = [pr.nama for _, pr in item if not pr.umur_simpan_hari]
    if tanpa_umur:
        return {"ok": False, "pesan": "Umur simpan belum diisi untuk: " + ", ".join(tanpa_umur),
                "data": None}

    batch_ids = []
    for d, pr in item:
        r = catat_barang_masuk_di(s, pr.id, d.qty_final,
                                  tanggal + timedelta(days=pr.umur_simpan_hari),
                                  d.harga_beli, tanggal)
        if not r["ok"]:
            return {"ok": False, "pesan": f"Gagal mencatat {pr.nama}: {r['pesan']}", "data": None}
        batch_ids.append(r["data"]["batch_id"])
        pr.harga_beli_terakhir = d.harga_beli
    p.status = "diterima"
    return {"ok": True, "pesan": f"Pesanan diterima, {len(batch_ids)} batch baru dibuat",
            "data": {"pesanan_id": pesanan_id, "batch_id": batch_ids}}


def terima_pesanan(pesanan_id: int) -> dict:
    """Fungsi KONTRAK 2.2 (dipakai Dhea)."""
    return _jalankan(terima_pesanan_di, pesanan_id)
