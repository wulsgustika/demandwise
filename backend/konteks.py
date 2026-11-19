"""
backend/konteks.py - "ruang data" milik siapa yang sedang dipakai (multi-pengguna).

Dua mode berjalan berdampingan:

* MODE DEMO      : akun demonstrasi (mis. `pemilik` / demo123). Melihat dan menulis data
                   dummy presentasi, yaitu semua baris dengan kolom user_id = NULL.
                   Data dummy lama TIDAK diubah sama sekali (kolom user_id-nya memang kosong).
* MODE PENGGUNA  : akun yang dibuat lewat "Buat akun". Hanya melihat dan menulis baris
                   dengan user_id = id akunnya sendiri. Akun baru mulai dari kosong.

Ruang aktif ditentukan berurutan:
  1. `pakai_ruang(...)` / `pakai_pengguna(user_id)` (untuk skrip dan tes),
  2. Streamlit: st.session_state[KUNCI_SESI] yang dipasang saat login (lihat app.py),
     kalau belum login -> ruang TERKUNCI (tidak bisa membaca/menulis data apa pun),
  3. selain itu (skrip/tes lama tanpa login) -> ruang DEMO, sama persis dengan perilaku lama.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

KUNCI_SESI = "_dw_ruang_data"


@dataclass(frozen=True)
class Ruang:
    """user_id=None -> data demo; user_id=n -> data milik akun n; user_id=-1 -> terkunci."""
    user_id: int | None
    nama: str = ""

    @property
    def demo(self) -> bool:
        return self.user_id is None

    @property
    def terkunci(self) -> bool:
        return self.user_id is not None and self.user_id < 0

    @property
    def kunci(self) -> str:
        """Kunci teks (untuk cache tampilan, dll.)."""
        return "demo" if self.demo else f"u{self.user_id}"


RUANG_DEMO = Ruang(None, "demo")
RUANG_TERKUNCI = Ruang(-1, "terkunci")

_TIDAK_DISET = object()
_ruang_paksa: ContextVar = ContextVar("dw_ruang_paksa", default=_TIDAK_DISET)


def _dalam_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except Exception:
        return False
    try:
        return get_script_run_ctx(suppress_warning=True) is not None
    except TypeError:  # streamlit lama tanpa argumen suppress_warning
        return get_script_run_ctx() is not None
    except Exception:
        return False


def ruang_aktif() -> Ruang:
    paksa = _ruang_paksa.get()
    if paksa is not _TIDAK_DISET:
        return paksa
    if _dalam_streamlit():
        try:
            import streamlit as st
            d = st.session_state.get(KUNCI_SESI)
        except Exception:
            d = None
        if isinstance(d, dict) and "user_id" in d:
            uid = d.get("user_id")
            return RUANG_DEMO if d.get("demo") or uid is None else Ruang(int(uid), str(d.get("nama", "")))
        return RUANG_TERKUNCI
    return RUANG_DEMO


def user_id_aktif() -> int | None:
    """None = data demo. Angka = id akun pemilik data."""
    return ruang_aktif().user_id


def adalah_demo() -> bool:
    return ruang_aktif().demo


def pastikan_boleh_tulis() -> Ruang:
    r = ruang_aktif()
    if r.terkunci:
        raise PermissionError("Silakan masuk (login) terlebih dahulu.")
    return r


# ---------------------------------------------------------------------------
# Menentukan ruang untuk sebuah akun
# ---------------------------------------------------------------------------
def akun_demo(user) -> bool:
    """Akun demo = ditandai akun_demo, atau akun lama tanpa email (akun dari data dummy)."""
    tanda = getattr(user, "akun_demo", None)
    if tanda is not None:
        return bool(tanda)
    return not getattr(user, "email", None)


def ruang_untuk_user(user_id: int) -> Ruang:
    """Baca tabel users lalu tentukan ruangnya. Akun tidak ada -> TERKUNCI."""
    from .db import get_session
    from .models import User
    with get_session() as s:
        u = s.get(User, int(user_id))
        if u is None:
            return RUANG_TERKUNCI
        return RUANG_DEMO if akun_demo(u) else Ruang(int(u.id), u.nama_usaha or "")


def data_sesi(ruang: Ruang) -> dict:
    """Bentuk sederhana untuk disimpan di st.session_state[KUNCI_SESI]."""
    return {"user_id": ruang.user_id, "demo": ruang.demo, "nama": ruang.nama}


@contextmanager
def pakai_ruang(ruang: Ruang):
    token = _ruang_paksa.set(ruang)
    try:
        yield ruang
    finally:
        _ruang_paksa.reset(token)


@contextmanager
def pakai_pengguna(user_id: int | None):
    """Jalankan kode sebagai akun `user_id` (None = demo). Untuk skrip & tes."""
    ruang = RUANG_DEMO if user_id is None else ruang_untuk_user(user_id)
    with pakai_ruang(ruang) as r:
        yield r
