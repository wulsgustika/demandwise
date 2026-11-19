"""Analitik: profit per produk, matriks fast/slow x margin, kalender musim laris, tren."""
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backend import mock_data as md
from backend.ml import musim
from components import ui

ui.require_role("Manajer", "Pemilik")
ui.page_header("Analitik & Musim", "Profit per produk, matriks Fast/Slow × Margin, kalender musim laris, dan tren penjualan.")

hari = st.segmented_control("Periode analisis", [30, 90, 180, 365], default=90, format_func=lambda x: f"{x} hari") or 90
g = musim.get_profit_produk(hari)
tab1, tab2, tab3, tab4 = st.tabs(["Profit per produk", "Matriks Fast/Slow × Margin", "Kalender musim laris", "Tren"])

with tab1:
    ui.kpi_row([
        dict(label="Laba bersih total", value=ui.rp_short(g.laba_bersih.sum()), tone="green"),
        dict(label="Margin rata-rata", value=f"{g.margin_pct.mean():.1f}%", tone="blue"),
        dict(label="Produk paling untung", value=g.iloc[0].nama, delta=ui.rp_short(g.iloc[0].laba_bersih), tone="orange"),
        dict(label="Total write-off", value=ui.rp_short(g.writeoff.sum()), tone="red"),
    ])
    n = st.slider("Jumlah produk ditampilkan", 5, 20, 10)
    mode = st.radio("Urutan", ["Paling untung", "Paling rendah"], horizontal=True)
    v = g.nlargest(n, "laba_bersih") if mode == "Paling untung" else g.nsmallest(n, "laba_bersih")
    v = v.sort_values("laba_bersih")
    fig = px.bar(v, x="laba_bersih", y="nama", orientation="h", color="margin_pct", color_continuous_scale=["#FFD8A8", ui.ORANGE, ui.BLUE, ui.NAVY], hover_data={"margin_pct": ":.1f", "qty": True})
    fig.update_layout(xaxis_title="Laba bersih (Rp)", yaxis_title=None, coloraxis_colorbar=dict(title="Margin %"))
    ui.show(fig, 120 + 32 * len(v), f"Laba bersih per produk · {hari} hari")

with tab2:
    st.caption("Fast/Slow = kecepatan jual dibanding median produk. Margin tinggi = ≥ 22%. Garis putus-putus adalah batas kuadran.")
    med = g.qty_per_hari.median()
    cmap = {"Bintang (Fast + Margin tinggi)": ui.GREEN, "Volume (Fast + Margin rendah)": ui.BLUE, "Niche untung (Slow + Margin tinggi)": ui.ORANGE, "Tinjau ulang (Slow + Margin rendah)": ui.RED}
    fig = px.scatter(g, x="qty_per_hari", y="margin_pct", size=np.maximum(g.omzet, 1), color="kuadran", hover_name="nama", color_discrete_map=cmap, size_max=38,
                     hover_data={"qty_per_hari": ":.1f", "margin_pct": ":.1f", "omzet": ":,.0f", "kuadran": False})
    fig.add_vline(x=med, line_dash="dash", line_color=ui.NAVY); fig.add_hline(y=22, line_dash="dash", line_color=ui.NAVY)
    for (x, y, tx) in [(.98, .98, "BINTANG"), (.98, .02, "VOLUME"), (.02, .98, "NICHE UNTUNG"), (.02, .02, "TINJAU ULANG")]:
        fig.add_annotation(xref="paper", yref="paper", x=x, y=y, text=f"<b>{tx}</b>", showarrow=False, font=dict(color=ui.MUTED, size=12), xanchor="right" if x > .5 else "left", yanchor="top" if y > .5 else "bottom")
    fig.update_layout(xaxis_title="Kecepatan jual (unit/hari)", yaxis_title="Margin (%)", xaxis_type="log", legend=dict(orientation="h", y=-.2))
    ui.show(fig, 480)
    pilih = st.multiselect("Lihat kuadran", list(cmap), default=list(cmap)[:1])
    if pilih:
        t = g[g.kuadran.isin(pilih)][["nama", "kategori", "qty_per_hari", "margin_pct", "laba_bersih", "kuadran"]].rename(columns={"nama": "Produk", "kategori": "Kategori", "qty_per_hari": "Unit/hari", "margin_pct": "Margin %", "laba_bersih": "Laba bersih", "kuadran": "Kuadran"})
        st.dataframe(t, hide_index=True, width="stretch", column_config={"Laba bersih": st.column_config.NumberColumn(format="Rp %d")})

with tab3:
    idx = musim.get_indeks_musim()
    st.caption("Indeks musim = rata-rata penjualan harian bulan tsb ÷ rata-rata seluruh bulan. **> 1,2** = musim laris (pemicu persiapan stok H-30).")
    fig = go.Figure(go.Heatmap(z=idx.values, x=idx.columns, y=idx.index, zmid=1, zmin=.5, zmax=2,
                               colorscale=[[0, "#DBEAFE"], [.4, "#FFFFFF"], [.6, "#FFD8A8"], [1, ui.ORANGE]], text=idx.values, texttemplate="%{text:.2f}",
                               hovertemplate="%{y} · %{x}: indeks %{z:.2f}<extra></extra>", colorbar=dict(title="Indeks")))
    fig.update_yaxes(autorange="reversed")
    ui.show(fig, 120 + 48 * len(idx))
    laris = [(k, m, float(idx.loc[k, m])) for k in idx.index if k != "Semua" for m in idx.columns if idx.loc[k, m] > 1.2]
    if laris:
        st.markdown("**Musim laris terdeteksi (indeks > 1,2):**")
        cols = st.columns(3)
        for i, (k, m, v) in enumerate(sorted(laris, key=lambda x: -x[2])[:9]):
            cols[i % 3].markdown(f"{ui.badge(f'{m}', 'orange')} {k} · **{v:.2f}**", unsafe_allow_html=True)
    ev = musim.get_trigger_musiman()
    if len(ev): st.warning("Pemicu aktif: " + ", ".join(f"{e.nama} (H-{e.h_minus})" for e in ev.itertuples()))

with tab4:
    tr = musim.get_tren_bulanan()
    c1, c2 = st.columns([1, 3])
    ukur = c1.radio("Ukuran", ["Omzet", "Unit terjual"])
    kat = c2.multiselect("Kategori", sorted(tr.kategori.unique()), default=sorted(tr.kategori.unique()))
    col = "omzet" if ukur == "Omzet" else "qty"
    v = tr[tr.kategori.isin(kat)]
    fig = px.line(v, x="periode", y=col, color="kategori", markers=True, color_discrete_sequence=ui.COLORWAY)
    fig.update_layout(xaxis_title=None, yaxis_title=ukur, hovermode="x unified")
    ui.show(fig, 400, f"Tren bulanan · {ukur}")
    tot = v.groupby("periode")[col].sum().reset_index()
    fig = px.area(tot, x="periode", y=col, color_discrete_sequence=[ui.BLUE])
    fig.update_layout(xaxis_title=None, yaxis_title=ukur)
    ui.show(fig, 260, "Total gabungan")
