"""Manajer: verifikasi laporan laba lalu teruskan ke Pemilik."""
import plotly.graph_objects as go
import streamlit as st

from backend import laporan_service
from components import ui

ui.require_role("Manajer")
user = ui.current_user()
ui.page_header("Verifikasi Laporan Laba", "Periksa HPP, biaya, dan write-off. Laporan terverifikasi otomatis diteruskan ke Pemilik.")

per = st.selectbox("Periode laporan", laporan_service.daftar_periode(), index=1)
lap = laporan_service.get_laporan_laba(per)
r, stt = lap["ringkasan"], laporan_service.get_status_laporan(per)
ui.kpi_row([
    dict(label="Omzet", value=ui.rp_short(r["omzet"]), tone="blue"),
    dict(label="HPP", value=ui.rp_short(r["hpp"]), tone="navy"),
    dict(label="Write-off + Biaya", value=ui.rp_short(r["writeoff"] + r["biaya"]), tone="orange"),
    dict(label="Laba bersih", value=ui.rp_short(r["laba_bersih"]), tone="green" if r["laba_bersih"] >= 0 else "red"),
])
c1, c2 = st.columns([1.2, 1], gap="large")
with c1:
    fig = go.Figure(go.Waterfall(x=["Omzet", "HPP", "Write-off", "Biaya operasional", "Laba bersih"], measure=["relative", "relative", "relative", "relative", "total"],
                                 y=[r["omzet"], -r["hpp"], -r["writeoff"], -r["biaya"], 0], connector=dict(line=dict(color="#9DB4E8")),
                                 increasing=dict(marker=dict(color=ui.BLUE)), decreasing=dict(marker=dict(color=ui.ORANGE)), totals=dict(marker=dict(color=ui.GREEN))))
    ui.show(fig, 340, f"Dari omzet ke laba bersih · {per}")
with c2:
    st.markdown(f"#### Status verifikasi\n{ui.badge(stt['status'])}", unsafe_allow_html=True)
    st.caption(f"Oleh: {stt['oleh']} · {stt['waktu']}")
    checks = {"Laba kotor = Omzet − HPP": True, "Write-off tercatat": r["writeoff"] >= 0, "Biaya operasional terisi": r["biaya"] > 0}
    for k, v in checks.items():
        st.markdown(("**Lulus** · " if v else "**Perlu dicek** · ") + k)
    cat = st.text_area("Catatan verifikasi (opsional)")
    if stt["status"] == "Terverifikasi":
        if st.button("Batalkan verifikasi", width="stretch"):
            laporan_service.batalkan_verifikasi(per); st.rerun()
    else:
        if st.button("Verifikasi & Kirim ke Pemilik", type="primary", width="stretch", disabled=r["biaya"] <= 0):
            ui.ok(laporan_service.verifikasi_laporan(per, user["nama"], cat)["pesan"]); st.rerun()
        if r["biaya"] <= 0: st.warning("Biaya operasional periode ini belum diinput.")
ui.section("Rincian per produk")
p = lap["produk"].copy()
st.dataframe(p[["nama", "kategori", "qty", "omzet", "hpp", "laba_kotor"]].rename(columns=str.title), hide_index=True, width="stretch", height=320,
             column_config={k: st.column_config.NumberColumn(format="Rp %d") for k in ("Omzet", "Hpp", "Laba_Kotor")})
