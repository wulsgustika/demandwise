"""backend/notifikasi.py - kirim notifikasi (KONTRAK 2.1, awalnya milik Nadia, kini Naila).

Fungsi dengan akhiran _di(s, ...) memakai sesi yang sudah ada (dipanggil dari
fungsi lain, commit dilakukan pemanggil). Fungsi tanpa akhiran membuka sesinya
sendiri untuk dipakai modul lain.
"""
from .models import LEVEL_NOTIF, Notifikasi


def kirim_notifikasi_di(s, jenis, level, judul, pesan, ref_tabel=None, ref_id=None) -> dict:
    if level not in LEVEL_NOTIF:
        return {"ok": False, "pesan": f"Level harus salah satu dari {LEVEL_NOTIF}", "data": None}
    if not jenis or not judul:
        return {"ok": False, "pesan": "Jenis dan judul wajib diisi", "data": None}
    n = Notifikasi(jenis=jenis, level=level, judul=judul, pesan=pesan,
                   ref_tabel=ref_tabel, ref_id=ref_id)
    s.add(n)
    s.flush()
    return {"ok": True, "pesan": "Notifikasi dikirim", "data": {"notif_id": n.id}}


def kirim_notifikasi(jenis, level, judul, pesan, ref_tabel=None, ref_id=None) -> dict:
    """Fungsi KONTRAK 2.1."""
    from .db import get_session
    try:
        with get_session() as s:
            hasil = kirim_notifikasi_di(s, jenis, level, judul, pesan, ref_tabel, ref_id)
            if hasil["ok"]:
                s.commit()
            return hasil
    except Exception as e:
        return {"ok": False, "pesan": f"Gagal mengirim notifikasi: {e}", "data": None}
