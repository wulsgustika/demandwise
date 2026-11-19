"""Pusat notifikasi per role."""
import streamlit as st

from backend import notifikasi_service as ns
from components import ui

user = ui.current_user()
role = user["role"]
ui.page_header("Pusat Notifikasi", f"Pemberitahuan untuk peran {role}.")
df = ns.get_notifikasi(role)
c1, c2, c3 = st.columns([1.4, 2, 1.2], vertical_alignment="bottom")
mode = c1.segmented_control("Tampilkan", ["Semua", "Belum dibaca"], default="Semua")
jenis = c2.multiselect("Jenis", sorted(df.jenis.unique()))
if c3.button("Tandai semua dibaca", width="stretch"):
    ns.tandai_semua_dibaca(role); st.rerun()
v = df
if mode == "Belum dibaca": v = v[~v.dibaca]
if jenis: v = v[v.jenis.isin(jenis)]
TONE = {"Risiko": "red", "Stok": "orange", "Pesanan": "blue", "Laporan": "green", "Tugas": "navy", "Musim": "yellow"}
st.caption(f"{len(v)} notifikasi · {int((~df.dibaca).sum())} belum dibaca")
if v.empty: ui.empty_state("Tidak ada notifikasi.")
for r in v.itertuples():
    a, b = st.columns([6, 1.2], vertical_alignment="center")
    with a:
        ui.row_card(r.pesan, r.waktu, "" if r.dibaca else "unread", ui.badge(r.jenis, TONE.get(r.jenis, "gray")))
    if not r.dibaca and b.button("Tandai dibaca", key=f"n_{r.id}", width="stretch"):
        ns.tandai_dibaca(int(r.id)); st.rerun()
