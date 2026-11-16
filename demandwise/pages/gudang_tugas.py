"""Staf Gudang: daftar tugas tindak lanjut (pindah batch ke rak depan, siapkan retur, dll.)."""
import streamlit as st

from backend import stok_service
from components import ui

ui.require_role("Staf Gudang", "Manajer")
user = ui.current_user()
ui.page_header("Tugas Tindak Lanjut", "Tugas dari keputusan Manajer atas batch berisiko kedaluwarsa.")

t = stok_service.get_tugas()
belum, selesai = t[t.status == "Belum"], t[t.status == "Selesai"]
k = st.columns(3)
k[0].markdown(ui.kpi_html("Belum dikerjakan", str(len(belum)), None, "orange"), unsafe_allow_html=True)
k[1].markdown(ui.kpi_html("Selesai", str(len(selesai)), None, "green"), unsafe_allow_html=True)
k[2].markdown(ui.kpi_html("Total tugas", str(len(t)), None, "navy"), unsafe_allow_html=True)

filt = st.segmented_control("Filter jenis", ["Semua"] + sorted(t.jenis.unique()), default="Semua")
ui.section("Perlu dikerjakan")
v = belum if filt in (None, "Semua") else belum[belum.jenis == filt]
if v.empty:
    ui.empty_state("Semua tugas sudah selesai. Kerja bagus!")
for r in v.itertuples():
    c1, c2 = st.columns([5, 1.3], vertical_alignment="center")
    with c1:
        ui.row_card(r.judul, f"{r.detail} · dibuat {r.dibuat}", right=ui.badge(r.jenis, "blue"))
    if c2.button("Tandai selesai", key=f"t_{r.id}", type="primary", width="stretch"):
        stok_service.selesaikan_tugas(int(r.id), user["nama"])
        ui.ok("Tugas ditandai selesai.")
        st.rerun()

with st.expander(f"Riwayat selesai ({len(selesai)})"):
    for r in selesai.itertuples():
        ui.row_card(r.judul, f"Selesai {r.selesai}", "done", ui.badge("Selesai"))
