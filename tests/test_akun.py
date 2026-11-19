"""Tes fitur akun: profil usaha, ganti password, lupa password, sesi login bertahan. SQLite sementara."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, update

from backend import akun, auth, db
from backend.akun import (buat_sesi, cabut_sesi, cek_sesi, ganti_password, get_profil, minta_reset_password,
                          reset_password, simpan_profil)
from backend.auth import daftar_akun, hash_password, login
from backend.models import Base, ProfilUsaha, SesiLogin, TokenResetPassword, User

PW = "rahasia123"


@pytest.fixture(autouse=True)
def db_sementara(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMANDWISE_DB_URL", f"sqlite:///{tmp_path / 'akun.sqlite'}")
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_SessionLocal", None)
    monkeypatch.setattr(auth, "_kolom_siap", False)
    Base.metadata.create_all(db.get_engine())
    with db.get_session() as s:   # akun demo seperti data dummy: tanpa email
        s.add(User(id=1, username="pemilik", password_hash=hash_password("demo123"), nama_usaha="Toko Demo"))
        s.commit()


@pytest.fixture
def kotak_surat(monkeypatch):
    """Tangkap email (kode reset) alih-alih benar-benar mengirim."""
    surat = []
    monkeypatch.setattr(akun, "_kirim_email", lambda tujuan, subjek, isi: surat.append((tujuan, isi)) or "email")
    return surat


def _akun(username="ayu_toko", email="ayu@contoh.com"):
    return daftar_akun("Toko Ayu", email, username, PW, PW)["data"]["user_id"]


def _kode(surat):
    return next(w for w in surat[-1][1].split() if w.isdigit() and len(w) == 6)


# ------------------------------------------------------------------ profil
def test_profil_kosong_lalu_diisi_bertahap():
    uid = _akun()
    p = get_profil(uid)["data"]
    assert p["terisi"] is False and p["telepon"] is None and p["alamat"] is None
    with db.get_session() as s:
        assert s.execute(select(ProfilUsaha)).first() is None          # belum ada baris sama sekali
    assert simpan_profil(uid, {"nama_usaha": "Toko Ayu"})["ok"] is False  # tidak ada yang diisi
    assert simpan_profil(uid, {"nama_usaha": "Toko Ayu", "telepon": "0812-3456-7890"})["ok"]
    p = get_profil(uid)["data"]
    assert p["terisi"] and p["telepon"] == "0812-3456-7890" and p["alamat"] is None
    r = simpan_profil(uid, {"nama_usaha": "Toko Ayu Jaya", "telepon": "0812-3456-7890", "alamat": "Jl. Mawar 1",
                            "kota": "Bandung", "logo": b"\x89PNG....", "logo_tipe": "image/png"})
    assert r["ok"] and r["data"]["nama_usaha"] == "Toko Ayu Jaya"
    p = get_profil(uid)["data"]
    assert p["kota"] == "Bandung" and p["logo"] == b"\x89PNG...." and p["nama_usaha"] == "Toko Ayu Jaya"
    assert login("ayu_toko", PW)["data"]["nama_usaha"] == "Toko Ayu Jaya"


def test_profil_validasi_dan_terpisah_per_akun():
    a, b = _akun(), _akun("budi_toko", "budi@contoh.com")
    assert not simpan_profil(a, {"nama_usaha": "Toko Ayu", "telepon": "telepon saya"})["ok"]
    assert not simpan_profil(a, {"nama_usaha": "Toko Ayu", "logo": b"x" * 1_000_001, "logo_tipe": "image/png"})["ok"]
    assert not simpan_profil(a, {"nama_usaha": "Toko Ayu", "logo": b"x", "logo_tipe": "image/gif"})["ok"]
    assert simpan_profil(a, {"nama_usaha": "Toko Ayu", "kota": "Bandung"})["ok"]
    assert get_profil(b)["data"]["terisi"] is False and get_profil(b)["data"]["kota"] is None


def test_akun_demo_dikunci():
    assert not simpan_profil(1, {"nama_usaha": "Ganti", "kota": "X"})["ok"]
    assert not ganti_password(1, "demo123", "baru12345", "baru12345")["ok"]
    assert minta_reset_password("pemilik@x.com")["ok"]                  # pesan umum, tidak ada kode
    assert login("pemilik", "demo123")["ok"]                              # login demo tetap sama


# ------------------------------------------------------------------ ganti password
def test_ganti_password_dan_sesi_lain_keluar():
    uid = _akun()
    sesi_ini = buat_sesi(uid)["data"]["token"]
    sesi_lain = buat_sesi(uid)["data"]["token"]
    assert ganti_password(uid, "salah1234", "baru12345", "baru12345")["pesan"] == "Password lama salah."
    assert not ganti_password(uid, PW, "pendek1", "pendek1")["ok"]
    assert not ganti_password(uid, PW, PW, PW)["ok"]                     # harus berbeda
    assert ganti_password(uid, PW, "baru12345", "baru12345", sesi_ini)["ok"]
    assert not login("ayu_toko", PW)["ok"] and login("ayu_toko", "baru12345")["ok"]
    assert cek_sesi(sesi_ini)["ok"] and not cek_sesi(sesi_lain)["ok"]


# ------------------------------------------------------------------ lupa password
def test_lupa_password_alur_lengkap(kotak_surat):
    uid = _akun()
    sesi = buat_sesi(uid)["data"]["token"]
    r = minta_reset_password("AYU@contoh.com")
    assert r["ok"] and kotak_surat[-1][0] == "ayu@contoh.com"
    kode = _kode(kotak_surat)
    salah = "000000" if kode != "000000" else "111111"
    assert not reset_password("ayu@contoh.com", salah, "baru12345", "baru12345")["ok"]
    assert reset_password("ayu@contoh.com", kode, "baru12345", "baru12345")["ok"]
    assert login("ayu@contoh.com", "baru12345")["ok"] and not login("ayu@contoh.com", PW)["ok"]
    assert not reset_password("ayu@contoh.com", kode, "lagi12345", "lagi12345")["ok"]   # sekali pakai
    assert not cek_sesi(sesi)["ok"]                                                    # sesi lama keluar


def test_lupa_password_email_tak_terdaftar_pesan_sama(kotak_surat):
    _akun()
    a, b = minta_reset_password("tidakada@contoh.com"), minta_reset_password("ayu@contoh.com")
    assert a["ok"] and b["ok"] and a["pesan"] == b["pesan"] and len(kotak_surat) == 1


def test_kode_kedaluwarsa_salah_berulang_dan_batas_permintaan(kotak_surat):
    uid = _akun()
    minta_reset_password("ayu@contoh.com")
    kode = _kode(kotak_surat)
    with db.get_session() as s:
        s.execute(update(TokenResetPassword).values(kedaluwarsa_pada=datetime.now() - timedelta(minutes=1)))
        s.commit()
    assert not reset_password("ayu@contoh.com", kode, "baru12345", "baru12345")["ok"]   # kedaluwarsa

    minta_reset_password("ayu@contoh.com")
    kode = _kode(kotak_surat)
    salah = "000000" if kode != "000000" else "111111"
    for _ in range(akun.MAKS_SALAH_KODE):
        reset_password("ayu@contoh.com", salah, "baru12345", "baru12345")
    assert not reset_password("ayu@contoh.com", kode, "baru12345", "baru12345")["ok"]   # hangus

    assert minta_reset_password("ayu@contoh.com")["ok"]                                 # permintaan ke-3
    assert not minta_reset_password("ayu@contoh.com")["ok"]                             # ke-4 ditolak


def test_mode_uji_tanpa_pengaturan_email(monkeypatch, capsys):
    monkeypatch.delenv("DEMANDWISE_EMAIL_USER", raising=False)
    _akun()
    r = minta_reset_password("ayu@contoh.com")
    assert r["ok"] and r["data"]["lewat"] == "terminal" and "Kode reset password" in capsys.readouterr().out


# ------------------------------------------------------------------ sesi bertahan
def test_sesi_buat_cek_cabut_dan_kedaluwarsa():
    uid = _akun()
    tok = buat_sesi(uid)["data"]["token"]
    r = cek_sesi(tok)
    assert r["ok"] and r["data"] == {"user_id": uid, "nama_usaha": "Toko Ayu", "mode_data": "pengguna"}
    assert not cek_sesi("token-palsu")["ok"] and not cek_sesi(None)["ok"]
    with db.get_session() as s:      # token disimpan sebagai hash, bukan teks aslinya
        assert s.execute(select(SesiLogin.token_hash)).scalar() != tok
    assert cabut_sesi(tok)["ok"] and not cek_sesi(tok)["ok"]
    tok2 = buat_sesi(uid)["data"]["token"]
    with db.get_session() as s:
        s.execute(update(SesiLogin).values(kedaluwarsa_pada=datetime.now() - timedelta(seconds=1)))
        s.commit()
    assert not cek_sesi(tok2)["ok"]
    assert cek_sesi(buat_sesi(1)["data"]["token"])["data"]["mode_data"] == "demo"
