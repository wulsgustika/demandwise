"""Evaluasi model: MAE, RMSE, MAPE & riwayat retraining."""
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backend.ml import evaluasi, prediksi
from components import ui

ui.require_role("Manajer", "Pemilik")
user = ui.current_user()
ui.page_header("Evaluasi Model", "Pantau akurasi prediksi (MAE, RMSE, MAPE) dan riwayat retraining.")

rt = evaluasi.get_riwayat_retrain()
cur, prev = rt.iloc[-1], rt.iloc[-2]
def dl(a, b, fmt="{:.2f}"):
    d = a - b
    return f"{'▼ membaik' if d < 0 else '▲ memburuk'} {fmt.format(abs(d))} vs {prev.versi}", "up" if d < 0 else "down"
ui.kpi_row([
    dict(label=f"MAE · {cur.versi}", value=f"{cur.mae:.2f}", delta=dl(cur.mae, prev.mae)[0], trend=dl(cur.mae, prev.mae)[1], tone="blue"),
    dict(label=f"RMSE · {cur.versi}", value=f"{cur.rmse:.2f}", delta=dl(cur.rmse, prev.rmse)[0], trend=dl(cur.rmse, prev.rmse)[1], tone="orange"),
    dict(label=f"MAPE · {cur.versi}", value=f"{cur.mape:.1f}%", delta=dl(cur.mape, prev.mape, "{:.1f}")[0], trend=dl(cur.mape, prev.mape)[1], tone="green"),
    dict(label="Koreksi manual terpakai", value=str(len(prediksi.get_koreksi())), delta="data latih berikutnya", tone="navy"),
])
c1, c2 = st.columns([1.5, 1], gap="large")
with c1:
    fig = go.Figure()
    fig.add_scatter(x=rt.versi, y=rt.mape, name="MAPE (%)", mode="lines+markers", line=dict(color=ui.GREEN, width=3), yaxis="y2")
    fig.add_bar(x=rt.versi, y=rt.mae, name="MAE", marker_color=ui.BLUE)
    fig.add_bar(x=rt.versi, y=rt.rmse, name="RMSE", marker_color=ui.ORANGE)
    fig.update_layout(barmode="group", yaxis=dict(title="MAE / RMSE"), yaxis2=dict(title="MAPE (%)", overlaying="y", side="right", showgrid=False), hovermode="x unified")
    ui.show(fig, 360, "Metrik per versi model")
with c2:
    ui.section("Retraining")
    st.markdown(f"Versi aktif: {ui.badge(cur.versi, 'navy')} &nbsp; {cur.algoritma}", unsafe_allow_html=True)
    st.caption(f"Terakhir dilatih {cur.tanggal} · {cur.data_latih:,} baris data".replace(",", "."))
    if user["role"] == "Manajer":
        if st.button("Jalankan Retraining", type="primary", width="stretch"):
            with st.spinner("Melatih ulang model…"):
                import time; time.sleep(1.2)
                r = evaluasi.jalankan_retrain(user["nama"])
            ui.ok(r["pesan"]); st.rerun()
    else:
        st.info("Retraining dijalankan oleh Manajer.")
ui.section("Akurasi per produk (backtest 28 hari)")
e = evaluasi.get_evaluasi_produk()
a, b = st.columns([1, 1.4], gap="large")
with a:
    t = e.sort_values("mape", ascending=False).rename(columns={"nama": "Produk", "kategori": "Kategori", "mae": "MAE", "rmse": "RMSE", "mape": "MAPE %"})
    st.dataframe(t, hide_index=True, width="stretch", height=380, column_config={"MAE": st.column_config.NumberColumn(format="%.2f"), "RMSE": st.column_config.NumberColumn(format="%.2f"), "MAPE %": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=40)})
with b:
    top = e.nlargest(12, "mape").sort_values("mape")
    fig = px.bar(top, x="mape", y="nama", orientation="h", color="mape", color_continuous_scale=["#9DB4E8", ui.ORANGE, ui.RED])
    fig.update_layout(xaxis_title="MAPE (%)", yaxis_title=None, coloraxis_showscale=False)
    ui.show(fig, 400, "12 produk paling sulit diprediksi")
ui.section("Riwayat retraining")
st.dataframe(rt.iloc[::-1].rename(columns=str.title), hide_index=True, width="stretch")
