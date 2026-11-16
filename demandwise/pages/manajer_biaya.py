"""Manajer: form biaya operasional."""
import plotly.express as px
import streamlit as st

from backend import laporan_service
from backend import mock_data as md
from components import ui

ui.require_role("Manajer")
user = ui.current_user()
ui.page_header("Biaya Operasional", "Input biaya rutin (gaji, sewa, listrik, dll.). Dipakai otomatis pada laporan laba.")

c1, c2 = st.columns([1, 1.5], gap="large")
with c1:
    with st.form("f_biaya", clear_on_submit=True):
        st.markdown("#### Tambah biaya")
        kat = st.selectbox("Kategori", ["Gaji Karyawan", "Sewa Tempat", "Listrik & Air", "Transportasi", "Pemasaran", "Perawatan", "Lain-lain"])
        tgl = st.date_input("Tanggal", value=md.TODAY, max_value=md.TODAY)
        jml = st.number_input("Jumlah (Rp)", min_value=0, step=50_000, value=0)
        ket = st.text_input("Keterangan", placeholder="contoh: Tagihan listrik Oktober")
        go = st.form_submit_button("Simpan Biaya", type="primary", width="stretch")
    if go:
        err = []
        if jml <= 0: err.append("Jumlah biaya harus lebih dari 0.")
        if len(ket.strip()) < 3: err.append("Keterangan wajib diisi.")
        if not ui.show_errors(err):
            ui.ok(laporan_service.simpan_biaya(kat, tgl, jml, ket, user["nama"])["pesan"])
b = laporan_service.get_biaya()
with c2:
    bulan = b.assign(periode=b.tanggal.dt.strftime("%Y-%m")).groupby(["periode", "kategori"]).jumlah.sum().reset_index()
    fig = px.bar(bulan, x="periode", y="jumlah", color="kategori", color_discrete_sequence=ui.COLORWAY)
    fig.update_layout(xaxis_title=None, yaxis_title="Rp", barmode="stack")
    ui.show(fig, 340, "Biaya operasional per bulan")

per = md.TODAY.strftime("%Y-%m")
tot = b[b.tanggal.dt.strftime("%Y-%m") == per].jumlah.sum()
ui.kpi_row([dict(label="Biaya bulan ini", value=ui.rp_short(tot), tone="orange"),
            dict(label="Rata-rata / bulan", value=ui.rp_short(b.groupby(b.tanggal.dt.strftime("%Y-%m")).jumlah.sum().mean()), tone="blue"),
            dict(label="Jumlah catatan", value=str(len(b)), tone="navy")])
ui.section("Riwayat biaya")
f = st.multiselect("Filter kategori", sorted(b.kategori.unique()))
t = b[b.kategori.isin(f)] if f else b
st.dataframe(t[["tanggal", "kategori", "jumlah", "keterangan", "oleh"]].rename(columns=str.title), hide_index=True, width="stretch", height=300,
             column_config={"Jumlah": st.column_config.NumberColumn(format="Rp %d"), "Tanggal": st.column_config.DateColumn(format="DD MMM YYYY")})
