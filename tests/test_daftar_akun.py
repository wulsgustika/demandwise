"""Tes daftar akun (email tersimpan di database). Memakai SQLite sementara."""
import pytest
from sqlalchemy import create_engine, text

from backend import auth, db
from backend.auth import daftar_akun, hash_password, login
from backend.models import Base, User


@pytest.fixture(autouse=True)
def db_sementara(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'tes.sqlite'}"
    monkeypatch.setenv("DEMANDWISE_DB_URL", url)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_SessionLocal", None)
    monkeypatch.setattr(auth, "_kolom_siap", False)
    Base.metadata.create_all(db.get_engine())


def _data(**kw):
    d = dict(nama_usaha="Toko Maju", email="Budi@Example.com", username="budi_01", password="rahasia123", konfirmasi="rahasia123")
    d.update(kw)
    return d


def test_daftar_berhasil_email_tersimpan_di_database():
    r = daftar_akun(**_data())
    assert r["ok"] is True and r["data"]["email"] == "budi@example.com"
    with db.get_session() as s:
        u = s.query(User).filter_by(username="budi_01").one()
        assert u.email == "budi@example.com" and u.nama_usaha == "Toko Maju"
        assert u.password_hash != "rahasia123"  # disimpan sebagai hash


def test_bisa_login_dengan_username_atau_email():
    daftar_akun(**_data())
    assert login("budi_01", "rahasia123")["ok"] is True
    assert login("BUDI@example.com", "rahasia123")["ok"] is True
    assert login("budi_01", "salah")["ok"] is False


def test_email_ganda_ditolak_tanpa_peduli_huruf_besar():
    assert daftar_akun(**_data())["ok"] is True
    r = daftar_akun(**_data(username="budi_02", email="BUDI@example.COM"))
    assert r["ok"] is False and "Email" in r["pesan"]


def test_username_ganda_ditolak():
    daftar_akun(**_data())
    r = daftar_akun(**_data(email="lain@example.com"))
    assert r["ok"] is False and "Username" in r["pesan"]


@pytest.mark.parametrize("kw", [
    dict(email="bukan-email"), dict(email="a@b"), dict(username="a b c d"), dict(username="abc"),
    dict(password="pendek1", konfirmasi="pendek1"), dict(password="hurufsaja", konfirmasi="hurufsaja"),
    dict(password="12345678", konfirmasi="12345678"), dict(konfirmasi="beda12345"), dict(nama_usaha="  "),
])
def test_input_tidak_valid_ditolak(kw):
    r = daftar_akun(**_data(**kw))
    assert r["ok"] is False and r["data"] is None
    with db.get_session() as s:
        assert s.query(User).count() == 0


def test_database_lama_tanpa_kolom_email_dimigrasi(tmp_path, monkeypatch):
    """Meniru demandwise.sqlite lama: tabel users tanpa kolom email, sudah berisi akun pemilik."""
    url = f"sqlite:///{tmp_path / 'lama.sqlite'}"
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(50) NOT NULL UNIQUE, "
                       "password_hash VARCHAR(255) NOT NULL, nama_usaha VARCHAR(150) NOT NULL, dibuat_pada DATETIME NOT NULL)"))
        c.execute(text("INSERT INTO users VALUES (1,'pemilik',:h,'Toko Berkah Jaya','2024-11-08 08:00:00')"),
                  {"h": hash_password("demo123")})
    monkeypatch.setenv("DEMANDWISE_DB_URL", url)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_SessionLocal", None)
    monkeypatch.setattr(auth, "_kolom_siap", False)

    assert login("pemilik", "demo123")["ok"] is True            # akun lama tetap bisa masuk
    assert daftar_akun(**_data())["ok"] is True                  # akun baru tersimpan
    assert daftar_akun(**_data(username="budi_02"))["ok"] is False  # email unik ditegakkan
    db.pastikan_kolom_email()                                    # aman dipanggil ulang
    with db.get_session() as s:
        assert s.query(User).count() == 2
