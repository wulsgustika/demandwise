"""Harga & laporan: rekomendasi harga, laporan HPP & laba, ekspor PDF/Excel."""
import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend import harga_service, laporan_service
from components import ui

ui.require_role("Manajer", "Pemilik")
ui.page_header("Harga & Laporan Laba", "Rekomendasi harga jual, laporan HPP dan laba, serta ekspor PDF / Excel.")

tab1, tab2 = st.tabs(["Rekomendasi harga", "Laporan HPP & laba"])
with tab1:
    h = harga_service.get_rekomendasi_harga()
    h["selisih"] = h.rekomendasi - h.harga_sekarang
    ui.kpi_row([
        dict(label="Harga perlu naik", value=str((h.selisih > 0).sum()), tone="orange"),
        dict(label="Harga perlu turun", value=str((h.selisih < 0).sum()), tone="blue"),
        dict(label="Tidak berubah", value=str((h.selisih == 0).sum()), tone="green"),
        dict(label="Margin rata-rata (rek.)", value=f"{h.margin_rek.mean():.1f}%", tone="navy"),
    ])
    c1, c2 = st.columns([1.2, 2])
    kat = c1.multiselect("Kategori", sorted(h.kategori.unique()))
    q = c2.text_input("Cari produk", key="q_harga")
    v = h.copy()
    if kat: v = v[v.kategori.isin(kat)]
    if q: v = v[v.nama.str.contains(q, case=False)]
    t = v[["nama", "kategori", "hpp", "harga_sekarang", "harga_pesaing", "tren_pct", "indeks_musim", "rekomendasi", "margin_rek", "alasan"]]
    st.dataframe(t.rename(columns={"nama": "Produk", "kategori": "Kategori", "hpp": "HPP", "harga_sekarang": "Harga kini", "harga_pesaing": "Pesaing", "tren_pct": "Tren %",
                                   "indeks_musim": "Indeks musim", "rekomendasi": "Rekomendasi", "margin_rek": "Margin %", "alasan": "Alasan"}),
                 hide_index=True, width="stretch", height=380,
                 column_config={c: st.column_config.NumberColumn(format="Rp %d") for c in ("HPP", "Harga kini", "Pesaing", "Rekomendasi")})
    st.caption("Persetujuan atau ubah harga manual dilakukan Pemilik di menu **Persetujuan Harga**.")
with tab2:
    per = st.selectbox("Periode", laporan_service.daftar_periode(), index=1)
    lap = laporan_service.get_laporan_laba(per)
    r, stt = lap["ringkasan"], laporan_service.get_status_laporan(per)
    st.markdown(f"Status laporan: {ui.badge(stt['status'])} &nbsp; <span style='color:#475569'>oleh {stt['oleh']}</span>", unsafe_allow_html=True)
    ui.kpi_row([
        dict(label="Omzet", value=ui.rp_short(r["omzet"]), tone="blue"),
        dict(label="HPP", value=ui.rp_short(r["hpp"]), tone="navy"),
        dict(label="Laba kotor", value=ui.rp_short(r["laba_kotor"]), tone="green"),
        dict(label="Laba bersih", value=ui.rp_short(r["laba_bersih"]), delta=f"write-off {ui.rp_short(r['writeoff'])} · biaya {ui.rp_short(r['biaya'])}", tone="green" if r["laba_bersih"] >= 0 else "red"),
    ])
    c1, c2 = st.columns([1.2, 1], gap="large")
    with c1:
        fig = go.Figure(go.Waterfall(x=["Omzet", "HPP", "Write-off", "Biaya", "Laba bersih"], measure=["relative"] * 4 + ["total"], y=[r["omzet"], -r["hpp"], -r["writeoff"], -r["biaya"], 0],
                                     connector=dict(line=dict(color="#9DB4E8")), increasing=dict(marker=dict(color=ui.BLUE)), decreasing=dict(marker=dict(color=ui.ORANGE)), totals=dict(marker=dict(color=ui.GREEN))))
        ui.show(fig, 330, "Waterfall laba")
    with c2:
        top = lap["produk"].nlargest(8, "laba_kotor").sort_values("laba_kotor")
        fig = go.Figure(go.Bar(x=top.laba_kotor, y=top.nama, orientation="h", marker_color=ui.BLUE, hovertemplate="%{y}: Rp %{x:,.0f}<extra></extra>"))
        ui.show(fig, 330, "Top 8 laba kotor")
    p = lap["produk"][["nama", "kategori", "qty", "omzet", "hpp", "laba_kotor"]].rename(columns={"nama": "Produk", "kategori": "Kategori", "qty": "Qty", "omzet": "Omzet", "hpp": "HPP", "laba_kotor": "Laba kotor"})
    st.dataframe(p, hide_index=True, width="stretch", height=300, column_config={c: st.column_config.NumberColumn(format="Rp %d") for c in ("Omzet", "HPP", "Laba kotor")})

    ui.section("Ekspor laporan")
    ring = pd.DataFrame([("Omzet", r["omzet"]), ("HPP", r["hpp"]), ("Laba kotor", r["laba_kotor"]), ("Write-off", r["writeoff"]), ("Biaya operasional", r["biaya"]), ("Laba bersih", r["laba_bersih"])], columns=["Komponen", "Rp"])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        ring.to_excel(xw, sheet_name="Ringkasan", index=False)
        p.to_excel(xw, sheet_name="Per Produk", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = 22
    def pdf_bytes() -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
        out = io.BytesIO(); sty = getSampleStyleSheet()
        els = [Image(str(ui.ASSETS / "logo.png"), 70, 70), Paragraph(f"Laporan HPP &amp; Laba - {per}", sty["Title"]),
               Paragraph(f"Status: {stt['status']}", sty["Normal"]), Spacer(1, 10)]
        def tbl(data, widths=None):
            t = Table(data, colWidths=widths, repeatRows=1)
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2A5B")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#9DB4E8")),
                                   ("FONTSIZE", (0, 0), (-1, -1), 8), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FF")])]))
            return t
        els.append(tbl([["Komponen", "Rp"]] + [[a, ui.rp(b)] for a, b in ring.itertuples(index=False)], [250, 150]))
        els += [Spacer(1, 14), Paragraph("Per produk", sty["Heading3"])]
        els.append(tbl([["Produk", "Qty", "Omzet", "HPP", "Laba kotor"]] + [[x.Produk, x.Qty, ui.rp(x.Omzet), ui.rp(x.HPP), ui.rp(x[5])] for x in p.itertuples(index=False)], [170, 40, 90, 90, 90]))
        SimpleDocTemplate(out, pagesize=A4, title=f"Laporan {per}").build(els)
        return out.getvalue()
    e1, e2, _ = st.columns([1, 1, 2])
    e1.download_button("Unduh Excel", buf.getvalue(), f"laporan_laba_{per}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", width="stretch")
    e2.download_button("Unduh PDF", pdf_bytes(), f"laporan_laba_{per}.pdf", "application/pdf", type="primary", width="stretch")
