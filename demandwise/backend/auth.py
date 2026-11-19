"""
auth.py - login (pemilik: Naila). Kontrak bagian 2.1.

login(username, password) -> {"ok": bool, "pesan": str, "data": {...} | None}
Tidak pernah memunculkan exception ke layar (aturan bagian 6).
"""
import bcrypt
from sqlalchemy import select

from .db import get_session
from .models import User

PESAN_GAGAL = "Username atau password salah"


def hash_password(password: str) -> str:
    """Ubah password polos jadi hash bcrypt (teks)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _cocok(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # hash di database bukan format bcrypt yang valid
        return False


def login(username: str, password: str) -> dict:
    try:
        username = (username or "").strip()
        if not username or not password:
            return {"ok": False, "pesan": "Username dan password wajib diisi", "data": None}

        with get_session() as s:
            user = s.execute(
                select(User).where(User.username == username)
            ).scalar_one_or_none()

            # Pesan sengaja sama untuk "user tidak ada" dan "password salah"
            if user is None or not _cocok(password, user.password_hash):
                return {"ok": False, "pesan": PESAN_GAGAL, "data": None}

            return {
                "ok": True,
                "pesan": "Login berhasil",
                "data": {"user_id": user.id, "nama_usaha": user.nama_usaha},
            }
    except Exception as e:  # jangan sampai error mentah muncul di layar
        return {"ok": False, "pesan": f"Gagal login: {type(e).__name__}", "data": None}


def atur_password(username: str, password_baru: str) -> dict:
    """Utilitas untuk dev: set ulang password seorang user (mis. jika hash dummy tidak valid)."""
    try:
        with get_session() as s:
            user = s.execute(
                select(User).where(User.username == username)
            ).scalar_one_or_none()
            if user is None:
                return {"ok": False, "pesan": "User tidak ditemukan", "data": None}
            user.password_hash = hash_password(password_baru)
            s.commit()
            return {"ok": True, "pesan": "Password diperbarui", "data": None}
    except Exception as e:
        return {"ok": False, "pesan": f"Gagal: {type(e).__name__}", "data": None}
