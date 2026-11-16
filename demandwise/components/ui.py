"""Komponen UI reusable DemandWise (Frontend B: identitas visual)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

NAVY, BLUE, SKY = "#0B2A5B", "#1F5FE0", "#3FB6FF"
ORANGE, GREEN, RED = "#FF8A1F", "#16A34A", "#DC2626"
INK, MUTED, LINE = "#0B1F44", "#475569", "#D6E2FF"
COLORWAY = [BLUE, ORANGE, GREEN, SKY, NAVY, "#8B5CF6", "#EC4899", "#14B8A6"]

# ---------------------------------------------------------------- tema
pio.templates["demandwise"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family="Inter, Poppins, sans-serif", size=13, color=INK),
        colorway=COLORWAY,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        xaxis=dict(gridcolor="#E5ECFA", linecolor="#9DB4E8", zerolinecolor="#E5ECFA"),
        yaxis=dict(gridcolor="#E5ECFA", linecolor="#9DB4E8", zerolinecolor="#E5ECFA"),
        hoverlabel=dict(bgcolor=NAVY, font=dict(color="#FFFFFF", size=13)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=50, b=10),
        title=dict(font=dict(family="Poppins, sans-serif", size=16, color=NAVY)),
    )
)
pio.templates.default = "demandwise"


def load_css() -> None:
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def style_fig(fig: go.Figure, height: int = 360, title: str | None = None) -> go.Figure:
    fig.update_layout(template="demandwise", height=height)
    if title:
        fig.update_layout(title=title)
    return fig


def show(fig: go.Figure, height: int = 360, title: str | None = None) -> None:
    st.plotly_chart(style_fig(fig, height, title), width="stretch",
                    config={"displaylogo": False, "responsive": True})


# ---------------------------------------------------------------- format
def rp(x: float) -> str:
    try:
        return "Rp " + f"{float(x):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "-"


def rp_short(x: float) -> str:
    x = float(x)
    a = abs(x)
    if a >= 1e9:
        return f"Rp {x/1e9:.2f} M".replace(".", ",")
    if a >= 1e6:
        return f"Rp {x/1e6:.1f} jt".replace(".", ",")
    if a >= 1e3:
        return f"Rp {x/1e3:.0f} rb"
    return f"Rp {x:.0f}"


def num(x: float) -> str:
    return f"{float(x):,.0f}".replace(",", ".")


# ---------------------------------------------------------------- komponen
def page_header(title: str, subtitle: str = "", icon: str = "") -> None:
    st.markdown(
        f"""<div class="dw-header">
        <div><h1>{title}</h1><p>{subtitle}</p></div></div>""",
        unsafe_allow_html=True,
    )


def section(title: str, hint: str = "") -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    if hint:
        st.markdown(f'<div class="section-hint">{hint}</div>', unsafe_allow_html=True)


def kpi_html(label: str, value: str, delta: str | None = None, tone: str = "blue",
             icon: str = "", trend: str = "flat") -> str:
    d = f'<div class="dl {trend}">{delta}</div>' if delta else ""
    return (f'<div class="kpi {tone}"><div class="lb"><span>{label}</span></div>'
            f'<div class="vl">{value}</div>{d}</div>')


def kpi_row(items: list[dict]) -> None:
    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        col.markdown(kpi_html(**it), unsafe_allow_html=True)


BADGE_TONE = {
    # status stok
    "Menipis": "red", "Overstock": "blue", "Aman": "green",
    # level kedaluwarsa
    "Kritis": "red", "Siaga": "orange", "Waspada": "yellow", "Normal": "green",
    # pesanan / laporan / tugas
    "Draf": "gray", "Review Manajer": "orange", "Persetujuan Pemilik": "orange",
    "Revisi": "red", "Disetujui": "green", "Dikirim ke Pemasok": "blue",
    "Jadwal Terkonfirmasi": "green", "Terverifikasi": "green", "Menunggu Verifikasi": "orange",
    "Terkonfirmasi": "green", "Menunggu Konfirmasi": "orange", "Selesai": "green", "Belum": "orange",
    "Ditolak": "red", "Menunggu": "orange",
}


def badge(text: str, tone: str | None = None) -> str:
    tone = tone or BADGE_TONE.get(text, "gray")
    return f'<span class="badge b-{tone}">{text}</span>'


_CELL = {
    "red": "background-color:#FEE2E2;color:#991B1B;font-weight:700",
    "orange": "background-color:#FFEDD5;color:#9A3412;font-weight:700",
    "yellow": "background-color:#FEF9C3;color:#713F12;font-weight:700",
    "green": "background-color:#DCFCE7;color:#14532D;font-weight:700",
    "blue": "background-color:#DBEAFE;color:#1E3A8A;font-weight:700",
    "gray": "background-color:#E2E8F0;color:#1E293B;font-weight:700",
}


def color_cells(df: pd.DataFrame, cols: list[str]):
    """Pandas Styler: warnai sel status agar kontras & mudah dibaca."""
    def f(v):
        return _CELL.get(BADGE_TONE.get(str(v), "gray"), "")
    return df.style.map(f, subset=cols)


def stepper(steps: list[str], current: str) -> None:
    idx = steps.index(current) if current in steps else -1
    html = '<div class="stepper">'
    for i, s in enumerate(steps):
        cls = "done" if i < idx else ("now" if i == idx else "")
        html += f'<div class="step {cls}">{"✓ " if i < idx else ""}{s}</div>'
    st.markdown(html + "</div>", unsafe_allow_html=True)


def row_card(title: str, sub: str = "", cls: str = "", right: str = "") -> None:
    st.markdown(
        f'<div class="row-card {cls}"><div style="display:flex;justify-content:space-between;gap:1rem">'
        f'<div><div class="t">{title}</div><div class="s">{sub}</div></div><div>{right}</div></div></div>',
        unsafe_allow_html=True,
    )


def empty_state(msg: str, icon: str = "") -> None:
    st.markdown(
        f'<div class="card" style="text-align:center;padding:2rem">'
        f'<div style="color:#475569;font-weight:600">{msg}</div></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- validasi & umpan balik
def show_errors(errors: list[str]) -> bool:
    """Tampilkan daftar error validasi. Return True bila ada error."""
    if errors:
        st.error("**Periksa kembali isian Anda:**\n\n" + "\n".join(f"- {e}" for e in errors))
        return True
    return False


def ok(msg: str) -> None:
    st.success(msg)
    st.toast(msg)


def fail(msg: str) -> None:
    st.error(msg)
    st.toast(msg)


def require_role(*roles: str) -> None:
    user = st.session_state.get("user")
    if not user or user["role"] not in roles:
        st.error("Anda tidak memiliki akses ke halaman ini.")
        st.stop()


def current_user() -> dict:
    return st.session_state["user"]
