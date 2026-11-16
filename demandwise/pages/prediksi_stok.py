"""Prediksi permintaan & status stok (menipis / overstock / aman), reorder point."""
import plotly.graph_objects as go
import streamlit as st

from backend import stok_service
from backend.ml import prediksi
from components import ui

ui.page_header("Prediksi & Status Stok", "Grafik historis vs prediksi per produk, serta status stok berdasarkan reorder point.")

stt = stok_service.get_stok_status()
prod = stok_service.get_produk()
ui.kpi_row([
    dict(label="Menipis", value=str((stt.status == "Menipis").sum()), delta="stok ≤ reorder point", tone="red"),
    dict(label="Aman", value=str((stt.status == "Aman").sum()), tone="green"),
    dict(label="Overstock", value=str((stt.status == "Overstock").sum()), delta="cover > 45 hari", tone="blue"),
    dict(label="Produk dipantau", value=str(len(stt)), tone="navy"),
])
tab1, tab2 = st.tabs(["Grafik per produk", "Tabel status stok"])
with tab1:
    c1, c2, c3 = st.columns([2, 1, 1])
    pn = c1.selectbox("Produk", prod.nama.tolist(), index=0)
    hor = c2.slider("Horizon prediksi (hari)", 7, 60, 30)
    hist = c3.slider("Riwayat (hari)", 30, 180, 90, step=10)
    p = prod.set_index("nama").loc[pn]
    pid = int(p.produk_id)
    h, f = prediksi.get_riwayat(pid, hist), prediksi.get_prediksi(pid, hor)
    r = stt.set_index("produk_id").loc[pid]
    ui.kpi_row([
        dict(label="Stok saat ini", value=ui.num(r.stok), delta=f"cukup {r.cover_hari} hari", tone="blue"),
        dict(label="Reorder point", value=ui.num(r.rop), delta=f"safety stock {r.safety}", tone="orange"),
        dict(label="Prediksi lead time", value=ui.num(r.pred_lt), delta=f"lead time {r.lead_time} hari", tone="navy"),
        dict(label="Status", value=r.status, tone={"Menipis": "red", "Aman": "green", "Overstock": "blue"}[r.status]),
    ])
    fig = go.Figure()
    fig.add_scatter(x=h.tanggal, y=h.qty, name="Penjualan aktual", line=dict(color=ui.NAVY, width=2), hovertemplate="%{x|%d %b}: %{y} unit<extra>Aktual</extra>")
    fig.add_scatter(x=f.tanggal, y=f.upper, line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=f.tanggal, y=f.lower, fill="tonexty", fillcolor="rgba(255,138,31,.22)", line=dict(width=0), name="Rentang prediksi (80%)", hoverinfo="skip")
    fig.add_scatter(x=f.tanggal, y=f.yhat, name="Prediksi", line=dict(color=ui.ORANGE, width=3, dash="dash"), hovertemplate="%{x|%d %b}: %{y:.1f} unit<extra>Prediksi</extra>")
    kor = f.dropna(subset=["koreksi"])
    if len(kor): fig.add_scatter(x=kor.tanggal, y=kor.koreksi, mode="markers", name="Koreksi manual", marker=dict(size=11, color=ui.GREEN, symbol="diamond"))
    fig.update_layout(yaxis_title="Unit / hari", hovermode="x unified")
    ui.show(fig, 400, f"{pn}: historis vs prediksi")
    st.caption(f"Total prediksi {hor} hari ke depan: **{f.yhat.sum():,.0f} unit** · stok {r.stok} unit akan {'habis sebelum hari ke-' + str(int((f.yhat.cumsum() >= r.stok).idxmax() + 1)) if f.yhat.sum() > r.stok else 'cukup sepanjang horizon'}.")
with tab2:
    c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
    sf = c1.multiselect("Status", ["Menipis", "Aman", "Overstock"], default=["Menipis", "Overstock"])
    kf = c2.multiselect("Kategori", sorted(stt.kategori.unique()))
    q = c3.text_input("Cari produk")
    v = stt.copy()
    if sf: v = v[v.status.isin(sf)]
    if kf: v = v[v.kategori.isin(kf)]
    if q: v = v[v.nama.str.contains(q, case=False)]
    t = v[["nama", "kategori", "stok", "rop", "safety", "pred_30", "cover_hari", "status"]].rename(columns={
        "nama": "Produk", "kategori": "Kategori", "stok": "Stok", "rop": "Reorder Point", "safety": "Safety Stock", "pred_30": "Prediksi 30 hr", "cover_hari": "Cukup (hari)", "status": "Status"})
    t["Prediksi 30 hr"] = t["Prediksi 30 hr"].round(0)
    st.dataframe(ui.color_cells(t, ["Status"]), hide_index=True, width="stretch", height=440)
    st.download_button("Unduh CSV", t.to_csv(index=False).encode("utf-8"), "status_stok.csv", "text/csv")
