"""Staf Gudang: stock opname (stok sistem vs fisik, selisih otomatis)."""
import pandas as pd
import streamlit as st

from backend import stok_service
from components import ui

ui.require_role("Staf Gudang", "Manajer")
user = ui.current_user()
ui.page_header("Stock Opname", "Bandingkan stok sistem dengan hitungan fisik. Selisih dihitung otomatis dan disimpan sebagai penyesuaian.")

df = stok_service.get_stok_sistem()
c1, c2 = st.columns([1, 2])
kat = c1.selectbox("Kategori", ["Semua"] + sorted(df.kategori.unique()))
cari = c2.text_input("Cari produk", placeholder="ketik nama atau kode…")
v = df.copy()
if kat != "Semua": v = v[v.kategori == kat]
if cari: v = v[v.nama.str.contains(cari, case=False) | v.kode.str.contains(cari, case=False)]

ver = st.session_state.get("opname_ver", 0)
edit = v[["produk_id", "kode", "nama", "stok_sistem"]].copy()
edit["Stok Fisik"] = edit.stok_sistem
st.caption("Ubah kolom **Stok Fisik** sesuai hasil hitung. Kolom lain terkunci.")
res = st.data_editor(
    edit, hide_index=True, width="stretch", height=360, key=f"opname_{kat}_{cari}_{ver}",
    disabled=["produk_id", "kode", "nama", "stok_sistem"],
    column_config={"produk_id": None, "kode": "Kode", "nama": st.column_config.TextColumn("Produk", width="large"),
                   "stok_sistem": st.column_config.NumberColumn("Stok Sistem"),
                   "Stok Fisik": st.column_config.NumberColumn("Stok Fisik", min_value=0, step=1, required=True)},
)
res = res.merge(v[["produk_id", "hpp"]], on="produk_id")
res["Selisih"] = res["Stok Fisik"] - res.stok_sistem
res["Nilai selisih"] = res.Selisih * res.hpp
beda = res[res.Selisih != 0]

ui.section("Hasil selisih (otomatis)")
k = st.columns(3)
k[0].markdown(ui.kpi_html("Produk dihitung", str(len(res)), None, "blue"), unsafe_allow_html=True)
k[1].markdown(ui.kpi_html("Produk berselisih", str(len(beda)), "perlu penyesuaian" if len(beda) else "semua sesuai", "orange" if len(beda) else "green"), unsafe_allow_html=True)
k[2].markdown(ui.kpi_html("Nilai selisih", ui.rp(beda["Nilai selisih"].sum()) if len(beda) else "Rp 0", "negatif = kehilangan", "red" if len(beda) and beda["Nilai selisih"].sum() < 0 else "green"), unsafe_allow_html=True)
if len(beda):
    t = beda[["nama", "stok_sistem", "Stok Fisik", "Selisih", "Nilai selisih"]].copy()
    t["Nilai selisih"] = t["Nilai selisih"].map(ui.rp)
    t["Arah"] = t.Selisih.map(lambda x: "Kurang" if x < 0 else "Lebih")
    st.dataframe(t.rename(columns={"nama": "Produk", "stok_sistem": "Sistem"}).style.map(
        lambda x: "background-color:#FEE2E2;color:#991B1B;font-weight:700" if x == "Kurang" else ("background-color:#DBEAFE;color:#1E3A8A;font-weight:700" if x == "Lebih" else ""), subset=["Arah"]),
        hide_index=True, width="stretch")
else:
    st.info("Belum ada selisih. Ubah Stok Fisik bila hitungan berbeda dari sistem.")

if st.button("Simpan Opname & Buat Penyesuaian", type="primary", disabled=len(beda) == 0):
    if (res["Stok Fisik"].isna()).any():
        ui.show_errors(["Stok Fisik tidak boleh kosong."])
    else:
        r = stok_service.simpan_opname([dict(produk_id=int(a), fisik=int(b)) for a, b in zip(beda.produk_id, beda["Stok Fisik"])], user["nama"])
        st.session_state["opname_ver"] = ver + 1
        st.toast(r["pesan"])
        st.rerun()

ui.section("Riwayat penyesuaian")
log = stok_service.get_opname_log()
if log.empty: ui.empty_state("Belum ada penyesuaian opname.")
else: st.dataframe(log.rename(columns=str.title), hide_index=True, width="stretch")
