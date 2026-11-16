"""Autentikasi (mock). Versi final: hash bcrypt + tabel users/roles."""
from __future__ import annotations

import hashlib
import hmac

from . import mock_data as md

# Menu per role -> key halaman (dipakai app.py)
AKSES = {
    "Staf Gudang": ["g_transaksi", "g_opname", "g_writeoff", "g_tugas", "prediksi", "risiko", "notif"],
    "Staf Pembelian": ["prediksi", "p_draf", "p_alur", "risiko", "notif"],
    "Manajer": ["dashboard", "prediksi", "risiko", "m_tindakan", "m_event", "m_biaya", "p_draf", "p_alur", "harga_lap", "m_verifikasi",
                "analitik", "koreksi", "evaluasi", "notif"],
    "Pemilik": ["dashboard", "prediksi", "risiko", "p_alur", "h_setuju", "harga_lap", "analitik", "evaluasi", "notif"],
}


def _h(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def authenticate(username: str, password: str) -> dict | None:
    u = md.USERS.get((username or "").strip().lower())
    if u and hmac.compare_digest(_h(password or ""), _h(u["pw"])):
        return dict(username=username.strip().lower(), nama=u["nama"], role=u["role"])
    return None
