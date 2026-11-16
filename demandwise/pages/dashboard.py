"""Dashboard utama (Manajer & Pemilik): KPI stok, penjualan, profit, peringatan aktif."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backend import laporan_service, stok_service
from backend import mock_data as md
from backend.ml import expiry, musim
from components import ui

ui.require_role("Manajer", "Pemilik")
ui.page_header("Dashboard Utama", "Ringkasan stok, penjualan, profit, dan peringatan aktif toko Anda.")

k = laporan_service.get_kpi_dashboard()
d = (k["omzet_30"] / k["omzet_prev"] - 1) * 100 if k["omzet_prev"] else 0
alert = k["menipis"] + k["kritis"] + k["siaga"]
ui.kpi_row([
    dict(label="Nilai stok", value=ui.rp_short(k["nilai_stok"]), delta=f"{k['menipis']} produk menipis · {k['overstock']} overstock", tone="blue"),
    dict(label="Penjualan 30 hari", value=ui.rp_short(k["omzet_30"]), delta=f"{'▲' if d >= 0 else '▼'} {abs(d):.1f}% vs 30 hari sebelumnya", tone="green", trend="up" if d >= 0 else "down"),
    dict(label=f"Laba bersih {k['periode']}", value=ui.rp_short(k["laba_bulan"]), delta="bulan penuh terakhir", tone="orange", trend="up" if k["laba_bulan"] >= 0 else "down"),
    dict(label="Peringatan aktif", value=str(alert), delta=f"{k['kritis']} kritis · {k['siaga']} siaga · {k['menipis']} stok menipis", tone="red", trend="down"),
])

rng = st.segmented_control("Rentang waktu", [30, 90, 180, 365], default=90, format_func=lambda x: f"{x} hari")
rng = rng or 90
s = musim.get_penjualan_enriched(rng)
c1, c2 = st.columns([1.7, 1], gap="large")
with c1:
    h = s.groupby("tanggal").agg(omzet=("omzet", "sum")).reset_index()
    h["MA7"] = h.omzet.rolling(7, min_periods=1).mean()
    fig = go.Figure()
    fig.add_bar(x=h.tanggal, y=h.omzet, name="Omzet harian", marker_color="#9DB4E8", hovertemplate="%{x|%d %b}: Rp %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=h.tanggal, y=h.MA7, name="Rata-rata 7 hari", line=dict(color=ui.ORANGE, width=3), hovertemplate="MA7: Rp %{y:,.0f}<extra></extra>")
    fig.update_layout(yaxis_title="Rp", hovermode="x unified")
    ui.show(fig, 360, "Tren penjualan")
with c2:
    kat = s.groupby("kategori").omzet.sum().reset_index().sort_values("omzet", ascending=False)
    fig = px.pie(kat, names="kategori", values="omzet", hole=.55, color_discrete_sequence=ui.COLORWAY)
    fig.update_traces(textinfo="percent", hovertemplate="%{label}<br>Rp %{value:,.0f}<extra></extra>")
    fig.update_layout(legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.08, yanchor="top"), margin=dict(b=70))
    ui.show(fig, 360, "Omzet per kategori")

c3, c4 = st.columns(2, gap="large")
with c3:
    top = s.groupby("nama").omzet.sum().nlargest(8).sort_values().reset_index()
    fig = px.bar(top, x="omzet", y="nama", orientation="h", color_discrete_sequence=[ui.BLUE])
    fig.update_layout(xaxis_title="Rp", yaxis_title=None)
    ui.show(fig, 340, "Top 8 produk (omzet)")
with c4:
    stt = stok_service.get_stok_status()
    cnt = stt.status.value_counts().reindex(["Menipis", "Aman", "Overstock"]).fillna(0).reset_index()
    cnt.columns = ["Status", "Produk"]
    fig = px.bar(cnt, x="Status", y="Produk", color="Status", text="Produk", color_discrete_map={"Menipis": ui.RED, "Aman": ui.GREEN, "Overstock": ui.BLUE})
    fig.update_layout(showlegend=False, xaxis_title=None)
    ui.show(fig, 340, "Status stok produk")

ui.section("Peringatan aktif", "Batch dan produk yang butuh perhatian segera.")
a, b = st.columns(2, gap="large")
with a:
    st.markdown("**Batch berisiko kedaluwarsa**")
    rk = expiry.get_risiko_kedaluwarsa()
    rk = rk[(rk.berisiko > 0) & (rk.level != "Normal")].head(6)
    if rk.empty: ui.empty_state("Tidak ada batch berisiko.")
    for r in rk.itertuples():
        ui.row_card(f"{r.nama} · {r.berisiko} unit berisiko", f"Batch {r.batch_id} · sisa {r.sisa_hari} hari · {ui.rp(r.nilai_risiko)}", right=ui.badge(r.level))
with b:
    st.markdown("**Stok menipis**")
    mn = stt[stt.status == "Menipis"].assign(gap=lambda x: x.stok - x.rop).sort_values("gap").head(6)
    if mn.empty: ui.empty_state("Semua stok aman.")
    for r in mn.itertuples():
        ui.row_card(f"{r.nama}", f"Stok {r.stok} · reorder point {r.rop} · cukup {r.cover_hari} hari", right=ui.badge("Menipis"))

ev = musim.get_event_musiman().sort_values("mulai")
ev = ev[ev.h_minus >= -3].head(2)
ui.section("Event musiman mendatang")
cols = st.columns(len(ev) or 1)
for col, e in zip(cols, ev.itertuples()):
    col.markdown(ui.kpi_html(e.nama, f"H-{e.h_minus}", f"{e.mulai:%d %b %Y} · lonjakan ×{e.lonjakan} · {e.status}", "orange" if e.h_minus <= 30 else "navy"), unsafe_allow_html=True)
