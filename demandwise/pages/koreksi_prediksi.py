"""Koreksi prediksi manual (dipakai sebagai data latih retraining)."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend import mock_data as md
from backend import stok_service
from backend.ml import prediksi
from components import ui

ui.require_role("Manajer")
user = ui.current_user()
ui.page_header("Koreksi Prediksi", "Ubah prediksi harian bila Anda tahu ada faktor yang belum dipahami model. Koreksi disimpan sebagai data latih.")

prod = stok_service.get_produk()
pn = st.selectbox("Produk", prod.nama.tolist())
pid = int(prod.set_index("nama").loc[pn].produk_id)
f = prediksi.get_prediksi(pid, 30)
asli = prediksi.get_prediksi(pid, 30, dengan_koreksi=False)
h = prediksi.get_riwayat(pid, 45)

c1, c2 = st.columns([1.8, 1], gap="large")
with c1:
    fig = go.Figure()
    fig.add_scatter(x=h.tanggal, y=h.qty, name="Aktual", line=dict(color=ui.NAVY, width=2))
    fig.add_scatter(x=asli.tanggal, y=asli.yhat, name="Prediksi model", line=dict(color=ui.ORANGE, width=3, dash="dash"))
    kor = f.dropna(subset=["koreksi"])
    if len(kor): fig.add_scatter(x=kor.tanggal, y=kor.koreksi, mode="markers+text", name="Koreksi manual", marker=dict(size=13, color=ui.GREEN, symbol="diamond"), text=kor.koreksi.round(0), textposition="top center")
    fig.update_layout(hovermode="x unified", yaxis_title="Unit / hari")
    ui.show(fig, 380, f"{pn}: prediksi 30 hari & koreksi")
with c2:
    with st.form("f_kor", clear_on_submit=True):
        st.markdown("#### Input koreksi")
        tgl = st.date_input("Tanggal prediksi", value=asli.tanggal.iloc[0].date(), min_value=asli.tanggal.iloc[0].date(), max_value=asli.tanggal.iloc[-1].date())
        mod = float(asli[asli.tanggal == pd.Timestamp(tgl)].yhat.iloc[0]) if len(asli[asli.tanggal == pd.Timestamp(tgl)]) else 0.0
        st.caption(f"Prediksi model pada tanggal ini: **{mod:.1f} unit**")
        nilai = st.number_input("Nilai koreksi (unit)", min_value=0.0, step=1.0, value=0.0)
        alasan = st.text_area("Alasan koreksi", placeholder="contoh: promo toko sebelah, acara sekolah, cuaca ekstrem")
        go_ = st.form_submit_button("Simpan Koreksi", type="primary", width="stretch")
    if go_:
        err = []
        if nilai <= 0: err.append("Nilai koreksi harus lebih dari 0.")
        if len(alasan.strip()) < 8: err.append("Alasan koreksi wajib diisi (min. 8 karakter).")
        if mod and nilai > mod * 5: err.append("Nilai koreksi lebih dari 5× prediksi model. Periksa kembali.")
        if not ui.show_errors(err):
            ui.ok(prediksi.simpan_koreksi(pid, tgl, nilai, alasan, user["nama"])["pesan"]); st.rerun()

ui.section("Riwayat koreksi")
k = prediksi.get_koreksi()
if k.empty: ui.empty_state("Belum ada koreksi manual.")
else:
    k = k.merge(prod[["produk_id", "nama"]], on="produk_id")
    for r in k.sort_values("waktu", ascending=False).itertuples():
        a, b = st.columns([6, 1], vertical_alignment="center")
        with a:
            ui.row_card(f"{r.nama} · {r.tanggal:%d %b %Y}: {r.prediksi_model:.0f} → {r.nilai:.0f} unit", f"{r.alasan} · {r.oleh} · {r.waktu}", right=ui.badge("Data latih", "green"))
        if b.button("Hapus", key=f"hk_{r.id}", width="stretch"): prediksi.hapus_koreksi(int(r.id)); st.rerun()
