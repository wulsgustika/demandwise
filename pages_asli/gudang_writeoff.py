"""Staf Gudang: catat barang kedaluwarsa yang dimusnahkan (jumlah x HPP)."""
import plotly.express as px
import streamlit as st

from backend import stok_service
from components import ui

ui.require_role("Staf Gudang", "Manajer")
user = ui.current_user()
ui.page_header("Barang Kedaluwarsa Dimusnahkan", "Catat write-off. Nilai kerugian = jumlah × HPP dan otomatis mengurangi laba.")

b = stok_service.get_batch()
kand = b[b.sisa_hari <= 14].sort_values("sisa_hari")
c1, c2 = st.columns([1.1, 1], gap="large")
with c1:
    with st.form("f_wo", clear_on_submit=True):
        st.markdown("#### Form pemusnahan")
        tampil_semua = st.checkbox("Tampilkan semua batch (bukan hanya ≤ 14 hari)")
        src = b if tampil_semua else kand
        opsi = src.batch_id.tolist()
        bid = st.selectbox("Batch", opsi, format_func=lambda x: f"{x} · {src.set_index('batch_id').loc[x, 'nama']} · sisa {src.set_index('batch_id').loc[x, 'sisa_hari']} hari · stok {src.set_index('batch_id').loc[x, 'qty']}") if opsi else None
        qty = st.number_input("Jumlah dimusnahkan", min_value=0, step=1, value=0)
        alasan = st.selectbox("Alasan", ["Kedaluwarsa", "Rusak tidak dapat dijual", "Retur pemasok ditolak"])
        konfirm = st.checkbox("Saya telah memusnahkan barang ini sesuai prosedur")
        go = st.form_submit_button("Catat Pemusnahan", type="primary")
    if go:
        err = []
        if not bid: err.append("Tidak ada batch yang dapat dipilih.")
        if qty <= 0: err.append("Jumlah harus lebih dari 0.")
        if not konfirm: err.append("Centang konfirmasi pemusnahan.")
        if not ui.show_errors(err):
            r = stok_service.catat_writeoff(bid, int(qty), alasan, user["nama"])
            (ui.ok if r["ok"] else ui.fail)(r["pesan"])
with c2:
    ui.section("Batch mendekati kedaluwarsa")
    if kand.empty: ui.empty_state("Tidak ada batch ≤ 14 hari.")
    else:
        for r in kand.head(5).itertuples():
            ui.row_card(f"{r.nama} · {r.qty} unit", f"Batch {r.batch_id} · kedaluwarsa {r.tgl_exp:%d %b %Y}",
                        right=ui.badge("Kritis" if r.sisa_hari <= 7 else "Siaga"))

wo = stok_service.get_writeoff()
ui.section("Riwayat pemusnahan")
k = st.columns(3)
k[0].markdown(ui.kpi_html("Total kerugian", ui.rp_short(wo.nilai.sum()), "semua periode", "red"), unsafe_allow_html=True)
k[1].markdown(ui.kpi_html("Unit dimusnahkan", ui.num(wo.qty.sum()), None, "orange"), unsafe_allow_html=True)
k[2].markdown(ui.kpi_html("Kejadian", str(len(wo)), None, "navy"), unsafe_allow_html=True)
if len(wo):
    st.dataframe(wo[["tanggal", "nama", "batch_id", "qty", "hpp", "nilai", "alasan", "oleh"]].rename(columns=str.title), hide_index=True, width="stretch",
                 column_config={"Hpp": st.column_config.NumberColumn(format="Rp %d"), "Nilai": st.column_config.NumberColumn(format="Rp %d")})
    top = wo.groupby("nama").nilai.sum().sort_values().reset_index()
    fig = px.bar(top, x="nilai", y="nama", orientation="h", color_discrete_sequence=[ui.RED])
    fig.update_layout(xaxis_title="Kerugian (Rp)", yaxis_title=None)
    ui.show(fig, 300, "Kerugian write-off per produk")
