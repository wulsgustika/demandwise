"""Ekspor tabel ke CSV, Excel, dan PDF. Hanya sisi tampilan; tidak menyentuh backend.

Pemakaian di halaman:
    from components import ekspor
    ekspor.tombol(df, "status_stok", "Status Stok", key="stok")

CSV memakai pustaka standar. Excel butuh `openpyxl`, PDF butuh `reportlab`
(keduanya ada di requirements.txt). Bila pustaka belum terpasang, tombolnya
tetap tampil dan memberi petunjuk instalasi, bukan membuat aplikasi error.
"""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import inspect

import streamlit as st

_ICON_OK = "icon" in inspect.signature(st.button).parameters


def _ik(nama: str) -> dict:
    return {"icon": f":material/{nama}:"} if _ICON_OK else {}


# Nama kolom yang ramah dibaca, selaras dengan components.ui
_LABEL = {"id": "ID", "produk_id": "ID Produk", "batch_id": "ID Batch", "nama_produk": "Produk",
          "pesanan_id": "ID Pesanan", "qty_final": "Qty Final", "qty_rekomendasi": "Qty Rekomendasi"}
_UANG = {"harga_beli_terakhir", "harga_jual", "hpp", "hpp_satuan", "harga_diskon", "harga_saat_ini",
         "harga_rekomendasi", "harga_pesaing_rata2", "jumlah", "penjualan", "laba_kotor", "laba_bersih",
         "biaya_operasional", "nilai_stok", "harga_beli", "subtotal"}


def _label(c: str) -> str:
    return _LABEL.get(c, str(c).replace("_", " ").strip().title())


def _bersih(df: pd.DataFrame) -> pd.DataFrame:
    """Salinan tabel siap ekspor: tanggal/waktu jadi teks, kolom berlabel ramah."""
    d = df.copy().reset_index(drop=True)
    for c in d.columns:
        if pd.api.types.is_datetime64_any_dtype(d[c]):
            d[c] = d[c].dt.strftime("%Y-%m-%d %H:%M").str.replace(" 00:00", "", regex=False)
        elif d[c].dtype == object:
            d[c] = d[c].map(lambda v: v.isoformat() if hasattr(v, "isoformat") else v)
    return d


def ke_csv(df: pd.DataFrame) -> bytes:
    # utf-8-sig supaya Excel Windows membaca huruf dan tanda baca dengan benar
    return _bersih(df).rename(columns=_label).to_csv(index=False).encode("utf-8-sig")


def ke_excel(df: pd.DataFrame, judul: str = "Data") -> bytes:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    d = _bersih(df)
    buf = io.BytesIO()
    nama_sheet = "".join(ch for ch in judul if ch not in "[]:*?/\\")[:31] or "Data"
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        d.rename(columns=_label).to_excel(xw, sheet_name=nama_sheet, index=False, startrow=2)
        ws = xw.sheets[nama_sheet]
        ws["A1"] = judul
        ws["A1"].font = Font(bold=True, size=14, color="022B4A")
        ws["A2"] = f"Dibuat {datetime.now():%d/%m/%Y %H:%M} · DemandWise"
        ws["A2"].font = Font(italic=True, size=9, color="5B7088")
        kepala = PatternFill("solid", fgColor="0057C4")
        for j, c in enumerate(d.columns, start=1):
            sel = ws.cell(row=3, column=j)
            sel.font = Font(bold=True, color="FFFFFF")
            sel.fill = kepala
            sel.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            lebar = max([len(_label(c))] + [len(str(v)) for v in d[c].head(200).tolist()]) + 3
            ws.column_dimensions[get_column_letter(j)].width = min(max(lebar, 10), 48)
            if c in _UANG or pd.api.types.is_float_dtype(d[c]):
                fmt = '#,##0' if c in _UANG else '#,##0.00'
                for i in range(4, 4 + len(d)):
                    ws.cell(row=i, column=j).number_format = fmt
        ws.freeze_panes = "A4"
        if len(d):
            ws.auto_filter.ref = f"A3:{get_column_letter(len(d.columns))}{3 + len(d)}"
    return buf.getvalue()


def _fmt_sel(c: str, v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    if isinstance(v, bool):
        return "Ya" if v else "Tidak"
    if isinstance(v, (int, float)):
        if c in _UANG:
            return "Rp" + f"{v:,.0f}".replace(",", ".")
        if isinstance(v, float) and not float(v).is_integer():
            return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{int(v):,}".replace(",", ".")
    return str(v)


def ke_pdf(df: pd.DataFrame, judul: str = "Laporan", ringkasan: list[tuple[str, str]] | None = None,
           maks_baris: int = 400) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    d = _bersih(df)
    potong = len(d) > maks_baris
    d = d.head(maks_baris)
    lebar_kolom = len(d.columns)
    ukuran = landscape(A4) if lebar_kolom > 5 else A4
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=ukuran, leftMargin=1.4 * cm, rightMargin=1.4 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm, title=judul)
    gaya = getSampleStyleSheet()
    judul_s = ParagraphStyle("j", parent=gaya["Title"], textColor=colors.HexColor("#022B4A"), fontSize=17, alignment=0)
    kecil = ParagraphStyle("k", parent=gaya["Normal"], textColor=colors.HexColor("#5B7088"), fontSize=8.5)
    sel_s = ParagraphStyle("s", parent=gaya["Normal"], fontSize=7.5 if lebar_kolom > 7 else 8.5, leading=10)
    kep_s = ParagraphStyle("h", parent=sel_s, textColor=colors.white, fontName="Helvetica-Bold")

    isi = [Paragraph(judul, judul_s),
           Paragraph(f"DemandWise · dibuat {datetime.now():%d/%m/%Y %H:%M} · {len(df)} baris", kecil),
           Spacer(1, 0.35 * cm)]
    if ringkasan:
        t = Table([[Paragraph(f"<b>{a}</b>", sel_s), Paragraph(b, sel_s)] for a, b in ringkasan], hAlign="LEFT",
                  colWidths=[5 * cm, 6 * cm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F8FD")),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9DCEB")),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        isi += [t, Spacer(1, 0.4 * cm)]
    if len(d):
        data = [[Paragraph(_label(c), kep_s) for c in d.columns]]
        for i in range(len(d)):
            data.append([Paragraph(_fmt_sel(c, d.iloc[i][c]).replace("&", "&amp;").replace("<", "&lt;"), sel_s)
                         for c in d.columns])
        tb = Table(data, repeatRows=1)
        tb.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0057C4")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F8FD")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9DCEB")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        isi.append(tb)
    else:
        isi.append(Paragraph("Tidak ada data.", kecil))
    if potong:
        isi += [Spacer(1, 0.3 * cm), Paragraph(f"Menampilkan {maks_baris} baris pertama. Gunakan Excel untuk data lengkap.", kecil)]

    def _kaki(canvas, dok):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#5B7088"))
        canvas.drawString(dok.leftMargin, 0.8 * cm, "DemandWise · Predict. Stock. Grow.")
        canvas.drawRightString(ukuran[0] - dok.rightMargin, 0.8 * cm, f"Halaman {dok.page}")
        canvas.restoreState()

    doc.build(isi, onFirstPage=_kaki, onLaterPages=_kaki)
    return buf.getvalue()


def _tersedia(modul: str) -> bool:
    try:
        __import__(modul)
        return True
    except Exception:
        return False


def tombol(df: pd.DataFrame | None, nama_file: str, judul: str, key: str,
           ringkasan: list[tuple[str, str]] | None = None) -> None:
    """Satu tombol 'Ekspor' (popover) berisi unduhan CSV, Excel, dan PDF untuk tabel `df`."""
    if df is None or len(df) == 0:
        return
    stamp = datetime.now().strftime("%Y%m%d")
    with st.popover("Ekspor", help="Unduh tabel ini sebagai PDF, Excel, atau CSV", **_ik("download")):
        st.caption(f"**{judul}** · {len(df)} baris")
        st.download_button("CSV", ke_csv(df), file_name=f"{nama_file}_{stamp}.csv", mime="text/csv",
                           key=f"dl_csv_{key}", **_ik("csv"), use_container_width=True)
        if _tersedia("openpyxl"):
            try:
                st.download_button("Excel (.xlsx)", ke_excel(df, judul), file_name=f"{nama_file}_{stamp}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key=f"dl_xlsx_{key}", **_ik("table_view"), use_container_width=True)
            except Exception as e:
                st.warning(f"Excel gagal dibuat: {e}")
        else:
            st.caption("Excel butuh library `openpyxl`: jalankan `pip install openpyxl`.")
        if _tersedia("reportlab"):
            kunci = f"_pdf_{key}"
            if st.button("Siapkan PDF", key=f"mk_pdf_{key}", **_ik("picture_as_pdf"), use_container_width=True):
                try:
                    st.session_state[kunci] = ke_pdf(df, judul, ringkasan)
                except Exception as e:
                    st.warning(f"PDF gagal dibuat: {e}")
            if st.session_state.get(kunci):
                st.download_button("Unduh PDF", st.session_state[kunci], file_name=f"{nama_file}_{stamp}.pdf",
                                   mime="application/pdf", key=f"dl_pdf_{key}", type="primary",
                                   **_ik("download"), use_container_width=True)
        else:
            st.caption("PDF butuh library `reportlab`: jalankan `pip install reportlab`.")
