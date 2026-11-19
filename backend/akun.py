"""
backend/akun.py - fitur akun: profil usaha, ganti password, lupa password, sesi login bertahan.

Semua fungsi mengembalikan {"ok": bool, "pesan": str, "data": ...} dan tidak pernah
melempar error ke layar (KONTRAK bagian 6).

Akun DEMO (mis. `pemilik`) dikunci: profil, password, dan reset password tidak bisa diubah,
supaya login dan data presentasi tetap utuh.

Email lupa password:
  Isi .streamlit/secrets.toml (atau variabel lingkungan) dengan akun pengirim, contoh Gmail:
      [email]
      user = "tokokamu@gmail.com"
      password = "app password 16 huruf"      # Google Account > Keamanan > App passwords
  Tanpa pengaturan itu aplikasi tetap jalan: kode reset DITAMPILKAN DI TERMINAL (mode uji).
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import func, select, update

from .db import get_engine, get_session
from .konteks import akun_demo
from .models import ProfilUsaha, SesiLogin, TokenResetPassword, User

log = logging.getLogger("demandwise.akun")

SESI_HARI = 7                 # lama "ingat saya"
KODE_RESET_MENIT = 15         # masa berlaku kode lupa password
MAKS_PERMINTAAN_KODE = 3      # per akun per KODE_RESET_MENIT
MAKS_SALAH_KODE = 5           # kode dianggap hangus setelah salah sekian kali
MAKS_LOGO_BYTE = 1_000_000
PESAN_DEMO = "Akun demo dikunci agar data dan login presentasi tetap utuh."

_POLA_TELEPON = re.compile(r"^\+?[0-9][0-9 \-]{6,19}$")
KOLOM_PROFIL = ["nama_pemilik", "telepon", "jenis_usaha", "alamat", "kota"]


def _hasil(ok, pesan, data=None, **lain):
    return {"ok": ok, "pesan": pesan, "data": data, **lain}


def _hash(teks: str) -> str:
    return hashlib.sha256(teks.encode("utf-8")).hexdigest()


def _siap():
    get_engine()   # memicu migrasi aman (membuat tabel akun bila belum ada)


def cek_password(password: str, konfirmasi: str | None = None) -> list[str]:
    """Aturan password yang sama dengan pendaftaran akun."""
    from .auth import MIN_PASSWORD
    galat = []
    password = password or ""
    if len(password) < MIN_PASSWORD:
        galat.append(f"Password minimal {MIN_PASSWORD} karakter.")
    elif password.isdigit() or password.isalpha():
        galat.append("Password harus berisi kombinasi huruf dan angka.")
    if konfirmasi is not None and password != konfirmasi:
        galat.append("Konfirmasi password tidak sama.")
    return galat


# ===========================================================================
# 1. Profil usaha
# ===========================================================================
def get_profil(user_id: int) -> dict:
    """Profil akun. Bagian yang belum diisi bernilai None (empty state)."""
    try:
        _siap()
        with get_session() as s:
            u = s.get(User, int(user_id))
            if u is None:
                return _hasil(False, "Akun tidak ditemukan")
            p = s.execute(select(ProfilUsaha).where(ProfilUsaha.user_id == u.id)).scalar_one_or_none()
            data = {"user_id": u.id, "username": u.username, "email": u.email, "nama_usaha": u.nama_usaha,
                    "akun_demo": akun_demo(u), "terisi": p is not None,
                    **{k: getattr(p, k) if p else None for k in KOLOM_PROFIL},
                    "logo": p.logo if p else None, "logo_tipe": p.logo_tipe if p else None,
                    "diubah_pada": p.diubah_pada if p else None}
            return _hasil(True, "OK", data)
    except Exception as e:
        return _hasil(False, f"Gagal membaca profil: {type(e).__name__}")


def simpan_profil(user_id: int, data: dict) -> dict:
    """Simpan bagian profil yang diisi. Kolom kosong dibiarkan kosong (boleh diisi belakangan).

    data: nama_usaha, nama_pemilik, telepon, jenis_usaha, alamat, kota,
          logo (bytes), logo_tipe ("image/png" | "image/jpeg"), hapus_logo (bool)
    """
    try:
        _siap()
        data = dict(data or {})
        bersih = {k: (" ".join(str(data.get(k) or "").split()) or None) for k in KOLOM_PROFIL}
        if data.get("alamat"):
            bersih["alamat"] = str(data["alamat"]).strip() or None
        galat = []
        nama_usaha = " ".join(str(data.get("nama_usaha") or "").split())
        if "nama_usaha" in data and len(nama_usaha) < 3:
            galat.append("Nama usaha minimal 3 karakter.")
        if bersih["telepon"] and not _POLA_TELEPON.match(bersih["telepon"]):
            galat.append("Nomor telepon hanya boleh angka, spasi, tanda -, dan + di depan (contoh 0812-3456-7890).")
        logo = data.get("logo")
        if logo is not None:
            if data.get("logo_tipe") not in ("image/png", "image/jpeg"):
                galat.append("Logo harus berformat PNG atau JPG.")
            elif len(logo) > MAKS_LOGO_BYTE:
                galat.append("Ukuran logo maksimal 1 MB.")
        if galat:
            return _hasil(False, " ".join(galat), galat=galat)

        with get_session() as s:
            u = s.get(User, int(user_id))
            if u is None:
                return _hasil(False, "Akun tidak ditemukan")
            if akun_demo(u):
                return _hasil(False, PESAN_DEMO)
            p = s.execute(select(ProfilUsaha).where(ProfilUsaha.user_id == u.id)).scalar_one_or_none()
            ada_isi = any(bersih.values()) or logo is not None
            if p is None and not ada_isi and (not nama_usaha or nama_usaha == u.nama_usaha):
                return _hasil(False, "Belum ada data profil yang diisi.")
            if nama_usaha and nama_usaha != u.nama_usaha:
                u.nama_usaha = nama_usaha
            if p is None and (ada_isi or data.get("hapus_logo")):
                p = ProfilUsaha(user_id=u.id)
                s.add(p)
            if p is not None:
                for k, v in bersih.items():
                    setattr(p, k, v)
                if logo is not None:
                    p.logo, p.logo_tipe = bytes(logo), data["logo_tipe"]
                elif data.get("hapus_logo"):
                    p.logo, p.logo_tipe = None, None
                p.diubah_pada = datetime.now()
            s.commit()
            return _hasil(True, "Profil tersimpan.", {"user_id": u.id, "nama_usaha": u.nama_usaha})
    except Exception as e:
        return _hasil(False, f"Gagal menyimpan profil: {type(e).__name__}")


# ===========================================================================
# 2. Ganti password
# ===========================================================================
def ganti_password(user_id: int, password_lama: str, password_baru: str, konfirmasi: str,
                   token_sesi_aktif: str | None = None) -> dict:
    """Ganti password. Semua sesi lain di perangkat lain otomatis keluar."""
    from .auth import _cocok, hash_password
    try:
        _siap()
        galat = cek_password(password_baru, konfirmasi)
        if password_baru and password_baru == password_lama:
            galat.append("Password baru harus berbeda dari password lama.")
        if galat:
            return _hasil(False, " ".join(galat), galat=galat)
        with get_session() as s:
            u = s.get(User, int(user_id))
            if u is None:
                return _hasil(False, "Akun tidak ditemukan")
            if akun_demo(u):
                return _hasil(False, PESAN_DEMO)
            if not _cocok(password_lama or "", u.password_hash):
                return _hasil(False, "Password lama salah.")
            u.password_hash = hash_password(password_baru)
            _cabut_semua_sesi(s, u.id, kecuali=token_sesi_aktif)
            s.commit()
            return _hasil(True, "Password berhasil diganti.")
    except Exception as e:
        return _hasil(False, f"Gagal mengganti password: {type(e).__name__}")


# ===========================================================================
# 3. Lupa password (kode 6 angka lewat email)
# ===========================================================================
def _pengaturan_email() -> dict | None:
    cfg = {}
    try:
        import streamlit as st
        if "email" in st.secrets:
            cfg = dict(st.secrets["email"])
    except Exception:
        pass
    cfg.setdefault("user", os.environ.get("DEMANDWISE_EMAIL_USER"))
    cfg.setdefault("password", os.environ.get("DEMANDWISE_EMAIL_PASSWORD"))
    if not cfg.get("user") or not cfg.get("password"):
        return None
    cfg.setdefault("host", os.environ.get("DEMANDWISE_EMAIL_HOST", "smtp.gmail.com"))
    cfg.setdefault("port", int(os.environ.get("DEMANDWISE_EMAIL_PORT", 587)))
    cfg.setdefault("pengirim", cfg["user"])
    return cfg


def _kirim_email(tujuan: str, subjek: str, isi: str) -> str:
    """Kirim email. Return 'email' bila terkirim, 'terminal' bila mode uji (tanpa pengaturan email)."""
    cfg = _pengaturan_email()
    if cfg is None:
        print(f"\n[DemandWise - MODE UJI EMAIL] ke {tujuan}\n{subjek}\n{isi}\n", flush=True)
        log.warning("Email belum diatur; isi email ditampilkan di terminal (mode uji).")
        return "terminal"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg["pengirim"], tujuan, subjek
    msg.set_content(isi)
    port = int(cfg["port"])
    if port == 465:
        with smtplib.SMTP_SSL(cfg["host"], port, timeout=20) as srv:
            srv.login(cfg["user"], cfg["password"])
            srv.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], port, timeout=20) as srv:
            srv.starttls()
            srv.login(cfg["user"], cfg["password"])
            srv.send_message(msg)
    return "email"


PESAN_KODE_TERKIRIM = ("Jika email tersebut terdaftar, kode reset 6 angka sudah dikirim. "
                       f"Kode berlaku {KODE_RESET_MENIT} menit.")


def minta_reset_password(email: str) -> dict:
    """Langkah 1: kirim kode ke email. Pesan sengaja sama walau email tidak terdaftar."""
    try:
        _siap()
        email = (email or "").strip().lower()
        if "@" not in email:
            return _hasil(False, "Masukkan email yang dipakai saat mendaftar.")
        sekarang = datetime.now()
        with get_session() as s:
            u = s.execute(select(User).where(func.lower(User.email) == email)).scalars().first()
            if u is None or akun_demo(u):
                return _hasil(True, PESAN_KODE_TERKIRIM, {"lewat": None})
            baru_saja = s.scalar(select(func.count(TokenResetPassword.id)).where(
                TokenResetPassword.user_id == u.id,
                TokenResetPassword.dibuat_pada >= sekarang - timedelta(minutes=KODE_RESET_MENIT)))
            if baru_saja >= MAKS_PERMINTAAN_KODE:
                return _hasil(False, f"Terlalu banyak permintaan kode. Coba lagi dalam {KODE_RESET_MENIT} menit.")
            # kode lama yang belum dipakai dihanguskan (hanya satu kode berlaku)
            s.execute(update(TokenResetPassword)
                      .where(TokenResetPassword.user_id == u.id, TokenResetPassword.dipakai_pada.is_(None))
                      .values(dipakai_pada=sekarang))
            kode = f"{secrets.randbelow(1_000_000):06d}"
            s.add(TokenResetPassword(user_id=u.id, kode_hash=_hash(f"{u.id}:{kode}"),
                                     kedaluwarsa_pada=sekarang + timedelta(minutes=KODE_RESET_MENIT)))
            s.commit()
            nama, tujuan = u.nama_usaha, u.email
        lewat = _kirim_email(
            tujuan, "Kode reset password DemandWise",
            f"Halo {nama},\n\nKode reset password DemandWise Anda: {kode}\n"
            f"Kode berlaku {KODE_RESET_MENIT} menit dan hanya bisa dipakai sekali.\n\n"
            "Abaikan email ini jika Anda tidak meminta reset password.")
        return _hasil(True, PESAN_KODE_TERKIRIM, {"lewat": lewat})
    except Exception as e:
        log.exception("Gagal mengirim kode reset")
        return _hasil(False, f"Kode belum bisa dikirim ({type(e).__name__}). Periksa pengaturan email.")


def reset_password(email: str, kode: str, password_baru: str, konfirmasi: str) -> dict:
    """Langkah 2: cocokkan kode lalu ganti password. Semua sesi login lama ikut keluar."""
    from .auth import hash_password
    try:
        _siap()
        galat = cek_password(password_baru, konfirmasi)
        kode = re.sub(r"\D", "", kode or "")
        if len(kode) != 6:
            galat.insert(0, "Kode harus 6 angka.")
        if galat:
            return _hasil(False, " ".join(galat), galat=galat)
        email = (email or "").strip().lower()
        sekarang = datetime.now()
        salah = _hasil(False, "Kode salah atau sudah kedaluwarsa. Minta kode baru bila perlu.")
        with get_session() as s:
            u = s.execute(select(User).where(func.lower(User.email) == email)).scalars().first()
            if u is None or akun_demo(u):
                return salah
            t = s.execute(select(TokenResetPassword).where(
                TokenResetPassword.user_id == u.id, TokenResetPassword.dipakai_pada.is_(None),
                TokenResetPassword.kedaluwarsa_pada > sekarang)
                .order_by(TokenResetPassword.id.desc())).scalars().first()
            if t is None or t.percobaan >= MAKS_SALAH_KODE:
                return salah
            if not secrets.compare_digest(t.kode_hash, _hash(f"{u.id}:{kode}")):
                t.percobaan += 1
                s.commit()
                return salah
            t.dipakai_pada = sekarang
            u.password_hash = hash_password(password_baru)
            _cabut_semua_sesi(s, u.id)
            s.commit()
            return _hasil(True, "Password berhasil direset. Silakan masuk dengan password baru.")
    except Exception as e:
        return _hasil(False, f"Gagal mereset password: {type(e).__name__}")


# ===========================================================================
# 4. Sesi login bertahan (token di cookie browser, hash token di tabel sesi_login)
# ===========================================================================
def buat_sesi(user_id: int, hari: int = SESI_HARI) -> dict:
    try:
        _siap()
        token = secrets.token_urlsafe(32)
        with get_session() as s:
            s.add(SesiLogin(user_id=int(user_id), token_hash=_hash(token),
                            kedaluwarsa_pada=datetime.now() + timedelta(days=hari)))
            s.commit()
        return _hasil(True, "Sesi dibuat", {"token": token, "hari": hari})
    except Exception as e:
        return _hasil(False, f"Gagal membuat sesi: {type(e).__name__}")


def cek_sesi(token: str | None) -> dict:
    """Token cookie masih berlaku? Kalau ya, kembalikan data login yang sama dengan login()."""
    try:
        if not token:
            return _hasil(False, "Tidak ada sesi")
        _siap()
        sekarang = datetime.now()
        with get_session() as s:
            ss = s.execute(select(SesiLogin).where(SesiLogin.token_hash == _hash(token))).scalar_one_or_none()
            if ss is None or ss.dicabut_pada is not None or ss.kedaluwarsa_pada <= sekarang:
                return _hasil(False, "Sesi berakhir, silakan masuk kembali")
            u = s.get(User, ss.user_id)
            if u is None:
                return _hasil(False, "Akun tidak ditemukan")
            ss.terakhir_dipakai = sekarang
            s.commit()
            return _hasil(True, "Sesi berlaku", {"user_id": u.id, "nama_usaha": u.nama_usaha,
                                                 "mode_data": "demo" if akun_demo(u) else "pengguna"})
    except Exception as e:
        return _hasil(False, f"Gagal memeriksa sesi: {type(e).__name__}")


def cabut_sesi(token: str | None) -> dict:
    """Keluar: sesi ditandai dicabut (baris tetap tersimpan sebagai riwayat)."""
    try:
        if not token:
            return _hasil(True, "Tidak ada sesi")
        _siap()
        with get_session() as s:
            s.execute(update(SesiLogin).where(SesiLogin.token_hash == _hash(token), SesiLogin.dicabut_pada.is_(None))
                      .values(dicabut_pada=datetime.now()))
            s.commit()
        return _hasil(True, "Sesi diakhiri")
    except Exception as e:
        return _hasil(False, f"Gagal mengakhiri sesi: {type(e).__name__}")


def _cabut_semua_sesi(s, user_id: int, kecuali: str | None = None) -> None:
    q = update(SesiLogin).where(SesiLogin.user_id == user_id, SesiLogin.dicabut_pada.is_(None))
    if kecuali:
        q = q.where(SesiLogin.token_hash != _hash(kecuali))
    s.execute(q.values(dicabut_pada=datetime.now()))
