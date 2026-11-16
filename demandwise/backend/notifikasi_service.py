"""Notifikasi lintas modul: kirim_notifikasi(role, jenis, pesan)."""
from __future__ import annotations

import pandas as pd

from .state import store, now, next_id


def kirim_notifikasi(role: str, jenis: str, pesan: str) -> int:
    nid = next_id("notif")
    store()["notifikasi"].insert(0, dict(id=nid, role=role, jenis=jenis, pesan=pesan, waktu=now(), dibaca=False))
    return nid


def get_notifikasi(role: str, hanya_belum: bool = False) -> pd.DataFrame:
    rows = [n for n in store()["notifikasi"] if n["role"] in (role, "Semua")]
    df = pd.DataFrame(rows, columns=["id", "role", "jenis", "pesan", "waktu", "dibaca"])
    if hanya_belum:
        df = df[~df.dibaca]
    return df.sort_values("waktu", ascending=False).reset_index(drop=True)


def jumlah_belum_dibaca(role: str) -> int:
    return sum(1 for n in store()["notifikasi"] if n["role"] in (role, "Semua") and not n["dibaca"])


def tandai_dibaca(notif_id: int) -> None:
    for n in store()["notifikasi"]:
        if n["id"] == notif_id:
            n["dibaca"] = True


def tandai_semua_dibaca(role: str) -> None:
    for n in store()["notifikasi"]:
        if n["role"] in (role, "Semua"):
            n["dibaca"] = True
