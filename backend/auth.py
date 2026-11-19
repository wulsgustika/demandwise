"""
auth.py - login (pemilik: Naila). Kontrak bagian 2.1.

login(username, password) -> {"ok": bool, "pesan": str, "data": {...} | None}
Tidak pernah memunculkan exception ke layar (aturan bagian 6).
"""
import re

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .db import get_engine, get_session
from .konteks import akun_demo
from .models import User

PESAN_GAGAL = "Username atau password salah"
_POLA_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
_POLA_USERNAME = re.compile(r"^[A-Za-z0-9_.]{4,30}$")
MIN_PASSWORD = 8
_kolom_siap = False


def _siapkan_kolom() -> None:
    """Pastikan kolom users.email ada (database lama). Dijalankan sekali per proses."""
    global _kolom_siap
    if not _kolom_siap:
        get_engine()   # memicu migrasi aman (users.email, users.akun_demo, kolom user_id)
        _kolom_siap = True


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
        _siapkan_kolom()

        with get_session() as s:
            # Boleh masuk memakai username ATAU email yang didaftarkan.
            user = s.execute(
                select(User).where(
                    (User.username == username) | (func.lower(User.email) == username.lower())
                )
            ).scalars().first()

            # Pesan sengaja sama untuk "user tidak ada" dan "password salah"
            if user is None or not _cocok(password, user.password_hash):
                return {"ok": False, "pesan": PESAN_GAGAL, "data": None}

            demo = akun_demo(user)
            return {
                "ok": True,
                "pesan": "Login berhasil",
                # mode_data: "demo" = data dummy presentasi, "pengguna" = data milik akun ini saja
                "data": {"user_id": user.id, "nama_usaha": user.nama_usaha,
                         "mode_data": "demo" if demo else "pengguna"},
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


def daftar_akun(nama_usaha: str, email: str, username: str, password: str, konfirmasi: str | None = None) -> dict:
    """Buat akun baru. Email disimpan (huruf kecil) di tabel users.

    Mengembalikan {"ok": bool, "pesan": str, "data": {"user_id", "nama_usaha", "email", "username"} | None}.
    Tidak pernah memunculkan exception ke layar (aturan bagian 6).
    """
    try:
        nama_usaha = " ".join((nama_usaha or "").split())
        email = (email or "").strip().lower()
        username = (username or "").strip()
        password = password or ""

        galat = []
        if len(nama_usaha) < 3:
            galat.append("Nama usaha minimal 3 karakter.")
        if not _POLA_EMAIL.match(email) or len(email) > 255:
            galat.append("Format email tidak valid (contoh: nama@email.com).")
        if not _POLA_USERNAME.match(username):
            galat.append("Username 4-30 karakter: huruf, angka, titik, atau garis bawah (tanpa spasi).")
        if len(password) < MIN_PASSWORD:
            galat.append(f"Password minimal {MIN_PASSWORD} karakter.")
        elif password.isdigit() or password.isalpha():
            galat.append("Password harus berisi kombinasi huruf dan angka.")
        if konfirmasi is not None and password != konfirmasi:
            galat.append("Konfirmasi password tidak sama.")
        if galat:
            return {"ok": False, "pesan": " ".join(galat), "data": None, "galat": galat}

        _siapkan_kolom()
        with get_session() as s:
            if s.execute(select(User.id).where(func.lower(User.email) == email)).first():
                return {"ok": False, "pesan": "Email ini sudah terdaftar. Silakan masuk atau gunakan email lain.", "data": None}
            if s.execute(select(User.id).where(User.username == username)).first():
                return {"ok": False, "pesan": "Username sudah dipakai. Pilih username lain.", "data": None}
            # Akun baru = akun pengguna sungguhan: datanya mulai KOSONG (tanpa data dummy).
            baru = User(username=username, password_hash=hash_password(password), nama_usaha=nama_usaha,
                        email=email, akun_demo=False)
            s.add(baru)
            try:
                s.commit()
            except IntegrityError:  # dua orang mendaftar bersamaan dengan data yang sama
                s.rollback()
                return {"ok": False, "pesan": "Email atau username sudah terdaftar.", "data": None}
            return {
                "ok": True,
                "pesan": "Akun berhasil dibuat. Silakan masuk.",
                "data": {"user_id": baru.id, "nama_usaha": baru.nama_usaha, "email": baru.email, "username": baru.username},
            }
    except Exception as e:
        return {"ok": False, "pesan": f"Gagal membuat akun: {type(e).__name__}", "data": None}
