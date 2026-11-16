"""Manajer: input / konfirmasi event musiman."""
import streamlit as st

from backend import mock_data as md
from backend.ml import musim
from components import ui

ui.require_role("Manajer")
user = ui.current_user()
ui.page_header("Event Musiman", "Konfirmasi event (Lebaran, Natal, tahun ajaran baru). Persiapan stok dipicu H-30 saat indeks musim > 1,2.")

e = musim.get_event_musiman().sort_values("mulai")
trig = musim.get_trigger_musiman()
if len(trig):
    for t in trig.itertuples():
        st.warning(f"**{t.nama}** dimulai H-{t.h_minus} · lonjakan ×{t.lonjakan}. Persiapan stok musiman aktif (tetap dibatasi masa simpan).")
ui.section("Daftar event")
for x in e.itertuples():
    c1, c2 = st.columns([5, 1.4], vertical_alignment="center")
    with c1:
        ui.row_card(x.nama, f"{x.mulai:%d %b %Y} – {x.selesai:%d %b %Y} · H-{x.h_minus} · kategori: {x.kategori} · lonjakan ×{x.lonjakan}",
                    "" if x.status == "Terkonfirmasi" else "unread", ui.badge(x.status))
    if x.status != "Terkonfirmasi" and c2.button("Konfirmasi", key=f"ev_{x.event_id}", type="primary", width="stretch"):
        musim.konfirmasi_event(int(x.event_id)); ui.ok(f"{x.nama} dikonfirmasi."); st.rerun()
ui.section("Tambah event baru")
with st.form("f_event", clear_on_submit=True):
    a, b = st.columns(2)
    nm = a.text_input("Nama event", placeholder="contoh: Imlek 2027")
    lj = b.slider("Perkiraan lonjakan permintaan (×)", 1.0, 4.0, 1.5, 0.1)
    c, d = st.columns(2)
    m = c.date_input("Mulai", value=md.TODAY)
    s = d.date_input("Selesai", value=md.TODAY)
    kat = st.multiselect("Kategori terdampak", md.KATEGORI)
    go = st.form_submit_button("Simpan Event", type="primary")
if go:
    err = []
    if len(nm.strip()) < 3: err.append("Nama event wajib diisi.")
    if s < m: err.append("Tanggal selesai tidak boleh sebelum tanggal mulai.")
    if not kat: err.append("Pilih minimal satu kategori terdampak.")
    if not ui.show_errors(err):
        ui.ok(musim.simpan_event(nm, m, s, kat, lj, user["nama"])["pesan"]); st.rerun()
