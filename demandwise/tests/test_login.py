"""Tes login. Memakai SQLite sementara, tidak menyentuh demandwise.sqlite/Neon."""
import pytest

from backend import db
from backend.auth import atur_password, hash_password, login
from backend.models import Base, User


@pytest.fixture(autouse=True)
def db_sementara(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'tes.sqlite'}"
    monkeypatch.setenv("DEMANDWISE_DB_URL", url)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_SessionLocal", None)
    Base.metadata.create_all(db.get_engine())
    with db.get_session() as s:
        s.add(User(username="pemilik", password_hash=hash_password("demo123"),
                   nama_usaha="Toko Berkah Jaya"))
        s.add(User(username="rusak", password_hash="GANTI_DENGAN_HASH_BCRYPT_DARI_demo123",
                   nama_usaha="Toko Rusak"))
        s.commit()


def test_login_berhasil():
    r = login("pemilik", "demo123")
    assert r["ok"] is True
    assert r["data"]["nama_usaha"] == "Toko Berkah Jaya"
    assert "user_id" in r["data"]


def test_password_salah():
    r = login("pemilik", "salah")
    assert r["ok"] is False and r["data"] is None


def test_user_tidak_ada():
    assert login("hantu", "demo123")["ok"] is False


def test_input_kosong():
    assert login("", "")["ok"] is False
    assert login("pemilik", "")["ok"] is False


def test_hash_dummy_tidak_valid_tidak_crash():
    assert login("rusak", "demo123")["ok"] is False


def test_atur_password_memperbaiki_hash_rusak():
    assert atur_password("rusak", "demo123")["ok"] is True
    assert login("rusak", "demo123")["ok"] is True
