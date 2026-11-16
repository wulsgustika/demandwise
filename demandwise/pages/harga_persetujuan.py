"""Pemilik/Manajer: persetujuan rekomendasi harga atau ubah harga manual."""
import pandas as pd
import streamlit as st

from backend import harga_service
from components import ui

ui.require_role("Pemilik", "Manajer")
user = ui.current_user()
ui.page_header("Persetujuan Harga Jual", "Setujui rekomendasi sistem atau ubah harga manual. Batas margin minimum dijaga otomatis.")

df = harga_service.get_rekomendasi_harga()
kat = st.selectbox("Kategori", ["Semua"] + sorted(df.kategori.unique()))
v = df if kat == "Semua" else df[df.kategori == kat]
v = v[(v.rekomendasi != v.harga_sekarang)] if st.toggle("Hanya yang berubah dari harga saat ini", value=True) else v
ver = st.session_state.get("harga_ver", 0)
ed = v[["produk_id", "nama", "hpp", "harga_sekarang", "harga_pesaing", "tren_pct", "rekomendasi", "alasan"]].copy()
ed.insert(0, "Setujui", False)
ed["Harga Final"] = ed.rekomendasi
ui.section("Daftar rekomendasi", "Centang untuk menyetujui. Ubah **Harga Final** bila ingin harga manual.")
res = st.data_editor(ed, hide_index=True, width="stretch", height=380, key=f"hg_{kat}_{len(v)}_{ver}",
                     disabled=[c for c in ed.columns if c not in ("Setujui", "Harga Final")],
                     column_config={"produk_id": None, "nama": st.column_config.TextColumn("Produk", width="medium"),
                                    "hpp": st.column_config.NumberColumn("HPP", format="Rp %d"), "harga_sekarang": st.column_config.NumberColumn("Harga kini", format="Rp %d"),
                                    "harga_pesaing": st.column_config.NumberColumn("Pesaing", format="Rp %d"), "tren_pct": st.column_config.NumberColumn("Tren %"),
                                    "rekomendasi": st.column_config.NumberColumn("Rekomendasi", format="Rp %d"), "alasan": "Alasan",
                                    "Harga Final": st.column_config.NumberColumn("Harga Final", format="Rp %d", min_value=0, step=100)})
sel = res[res.Setujui].merge(v[["produk_id", "kategori", "margin_min"]], on="produk_id")
if len(sel):
    sel["Margin final %"] = ((sel["Harga Final"] - sel.hpp) / sel["Harga Final"] * 100).round(1)
    sel["Batas min %"] = (sel.margin_min / (1 + sel.margin_min) * 100).round(1)
    sel["Status"] = sel.apply(lambda r: "Di bawah batas" if r["Harga Final"] < r.hpp * (1 + r.margin_min) else "Aman", axis=1)
    ui.section("Pratinjau margin")
    st.dataframe(sel[["nama", "Harga Final", "Margin final %", "Batas min %", "Status"]].rename(columns={"nama": "Produk"}).style.map(
        lambda x: "background-color:#FEE2E2;color:#991B1B;font-weight:700" if x == "Di bawah batas" else ("background-color:#DCFCE7;color:#14532D;font-weight:700" if x == "Aman" else ""), subset=["Status"]),
        hide_index=True, width="stretch")
    bawah = sel[sel.Status == "Di bawah batas"]
    izin = False
    if len(bawah):
        st.warning(f"{len(bawah)} item di bawah batas margin minimum.")
        izin = st.checkbox("Saya memahami risikonya dan tetap menerapkan harga di bawah margin minimum")
alasan = st.text_input("Alasan perubahan", value="Persetujuan rekomendasi harga")
if st.button("Terapkan Harga Terpilih", type="primary", disabled=len(sel) == 0):
    err = []
    if (sel["Harga Final"] <= sel.hpp).any(): err.append("Harga final tidak boleh sama atau di bawah HPP.")
    if len(sel) and (sel.Status == "Di bawah batas").any() and not izin: err.append("Centang persetujuan risiko untuk harga di bawah margin minimum.")
    if not ui.show_errors(err):
        for _, r in sel.iterrows(): harga_service.set_harga(int(r.produk_id), float(r["Harga Final"]), alasan, user["nama"])
        st.session_state["harga_ver"] = ver + 1
        st.toast(f"{len(sel)} harga diperbarui."); st.rerun()
ui.section("Riwayat perubahan harga")
lg = harga_service.get_harga_log()
if lg.empty: ui.empty_state("Belum ada perubahan harga pada sesi ini.")
else: st.dataframe(lg.rename(columns=str.title), hide_index=True, width="stretch",
                   column_config={"Lama": st.column_config.NumberColumn(format="Rp %d"), "Baru": st.column_config.NumberColumn(format="Rp %d")})
