"""Risiko kedaluwarsa: level waspada (H-30) / siaga (H-14) / kritis (H-7) + rekomendasi tindakan."""
import pandas as pd
import plotly.express as px
import streamlit as st

from backend.ml import expiry
from components import ui

ui.page_header("Risiko Kedaluwarsa", "Berisiko = stok batch − prediksi harian × sisa hari. Level: H-30 Waspada · H-14 Siaga · H-7 Kritis.")

r = expiry.get_risiko_kedaluwarsa()
rb = r[r.berisiko > 0]
ui.kpi_row([
    dict(label="Kritis (≤ 7 hari)", value=str(((rb.level == "Kritis")).sum()), delta="batch berisiko", tone="red"),
    dict(label="Siaga (≤ 14 hari)", value=str(((rb.level == "Siaga")).sum()), tone="orange"),
    dict(label="Waspada (≤ 30 hari)", value=str(((rb.level == "Waspada")).sum()), tone="blue"),
    dict(label="Nilai berisiko", value=ui.rp_short(rb.nilai_risiko.sum()), delta=f"{ui.num(rb.berisiko.sum())} unit", tone="navy"),
])
c1, c2, c3 = st.columns([1.5, 1.4, 1.3], vertical_alignment="bottom")
lv = c1.multiselect("Level", ["Kritis", "Siaga", "Waspada", "Normal"], default=["Kritis", "Siaga", "Waspada"])
kt = c2.multiselect("Kategori", sorted(r.kategori.unique()))
hb = c3.toggle("Hanya yang berisiko", value=True)
v = r.copy()
if lv: v = v[v.level.isin(lv)]
if kt: v = v[v.kategori.isin(kt)]
if hb: v = v[v.berisiko > 0]

a, b = st.columns([1.5, 1], gap="large")
with a:
    ui.section("Tabel batch", "Klik satu baris untuk melihat detail & jadwal diskon.")
    t = v[["batch_id", "nama", "rak", "qty", "tgl_exp", "sisa_hari", "proyeksi_laku", "berisiko", "nilai_risiko", "level", "rekomendasi", "keputusan"]].rename(columns={
        "batch_id": "Batch", "nama": "Produk", "rak": "Rak", "qty": "Stok", "tgl_exp": "Kedaluwarsa", "sisa_hari": "Sisa hari", "proyeksi_laku": "Proyeksi laku",
        "berisiko": "Berisiko", "nilai_risiko": "Nilai risiko", "level": "Level", "rekomendasi": "Rekomendasi", "keputusan": "Keputusan"})
    ev = st.dataframe(ui.color_cells(t, ["Level", "Keputusan"]), hide_index=True, width="stretch", height=420, on_select="rerun", selection_mode="single-row",
                      column_config={"Nilai risiko": st.column_config.NumberColumn(format="Rp %d"), "Kedaluwarsa": st.column_config.DateColumn(format="DD MMM YYYY")})
with b:
    ui.section("Sebaran risiko")
    g = v.groupby("level").berisiko.sum().reindex(["Kritis", "Siaga", "Waspada", "Normal"]).dropna().reset_index()
    fig = px.bar(g, x="level", y="berisiko", color="level", text="berisiko", color_discrete_map={"Kritis": ui.RED, "Siaga": ui.ORANGE, "Waspada": "#EAB308", "Normal": ui.GREEN})
    fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Unit berisiko")
    ui.show(fig, 300)
    sc = v[v.berisiko > 0]
    if len(sc):
        fig = px.scatter(sc, x="sisa_hari", y="nilai_risiko", size="berisiko", color="level", hover_name="nama", color_discrete_map={"Kritis": ui.RED, "Siaga": ui.ORANGE, "Waspada": "#EAB308", "Normal": ui.GREEN})
        fig.update_layout(xaxis_title="Sisa hari", yaxis_title="Nilai risiko (Rp)", showlegend=False)
        ui.show(fig, 280, "Waktu vs nilai risiko")

sel = ev.selection.rows if ev and ev.selection else []
if sel:
    bid = t.iloc[sel[0]]["Batch"]
    rek = expiry.get_rekomendasi_tindakan(bid)
    x = rek["baris"]
    ui.section(f"Detail: {x.nama} · batch {bid}")
    c1, c2 = st.columns([1, 1.3], gap="large")
    with c1:
        st.markdown(f"{ui.badge(x.level)} &nbsp; sisa **{x.sisa_hari} hari** · kedaluwarsa **{x.tgl_exp:%d %b %Y}**", unsafe_allow_html=True)
        st.markdown(f"- Stok batch: **{x.qty}** unit\n- Proyeksi laku: **{x.proyeksi_laku}** unit\n- Berisiko: **{x.berisiko}** unit ({ui.rp(x.nilai_risiko)})\n- Rekomendasi utama: **{rek['tindakan_utama']}**\n- Bundling dengan: **{rek['bundling']}**\n- Retur pemasok: **{'layak' if rek['retur_layak'] else 'tidak layak'}** ({x.pemasok})")
        st.info("Keputusan tindakan dilakukan Manajer di menu **Tindakan Batch Berisiko**.")
    with c2:
        d = pd.DataFrame(rek["diskon_bertahap"])
        fig = px.bar(d, x="tahap", y="harga", text=d.apply(lambda q: f"-{q.diskon}%<br>{ui.rp(q.harga)}", axis=1), color_discrete_sequence=[ui.BLUE])
        fig.add_hline(y=rek["harga_min"], line_dash="dash", line_color=ui.RED, annotation_text="HPP (batas bawah)", annotation_position="top left")
        fig.update_layout(xaxis_title="Tahap diskon", yaxis_title="Harga (Rp)", xaxis=dict(dtick=1))
        ui.show(fig, 320, "Diskon bertahap (tidak di bawah HPP)")
else:
    st.caption("Pilih satu baris pada tabel untuk melihat jadwal diskon bertahap dan rekomendasi lengkap.")
