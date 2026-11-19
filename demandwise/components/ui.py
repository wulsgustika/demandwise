"""Komponen UI DemandWise - tema mengikuti logo (cyan, navy, biru royal, oranye).

Hanya lapisan tampilan. Tidak ada pemanggilan backend di berkas ini.
"""
from __future__ import annotations

import base64
import inspect
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
from streamlit.errors import StreamlitAPIException

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# Palet dari logo
NAVY_D, NAVY, BLUE, CYAN, SKY = "#022B4A", "#03426E", "#0057C4", "#3DC4F2", "#DDF4FF"
ORANGE, GREEN, RED, AMBER = "#E07B0A", "#12A150", "#D92D20", "#F5A524"
INK, MUTED, LINE = "#0A2540", "#5B7088", "#D5E6F3"
COLORWAY = [BLUE, ORANGE, CYAN, NAVY, GREEN, "#7C5CFC", AMBER, "#E5528B"]

# ---------------------------------------------------------------- tema plotly
pio.templates["demandwise"] = go.layout.Template(
    layout=go.Layout(
        font=dict(family="Inter, 'Plus Jakarta Sans', sans-serif", size=12.5, color=INK),
        colorway=COLORWAY,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#EAF2F8", linecolor="#C9DCEB", zerolinecolor="#EAF2F8", tickfont=dict(color=MUTED)),
        yaxis=dict(gridcolor="#EAF2F8", linecolor="#C9DCEB", zerolinecolor="#EAF2F8", tickfont=dict(color=MUTED)),
        hoverlabel=dict(bgcolor=NAVY_D, font=dict(color="#FFFFFF", size=12.5), bordercolor=NAVY_D),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=12, r=12, t=56, b=12),
        title=dict(font=dict(family="'Plus Jakarta Sans', Inter, sans-serif", size=15, color=NAVY), x=0.02),
    )
)
pio.templates.default = "demandwise"

# ---------------------------------------------------------------- kompatibilitas versi Streamlit
_NEW: dict[str, bool] = {}


def wide(fn, *a, **kw):
    """Lebar penuh: `width='stretch'` (Streamlit baru) atau `use_container_width` (lama)."""
    k = getattr(fn, "__name__", str(fn))
    if _NEW.get(k) is not False:
        try:
            r = fn(*a, width="stretch", **kw)
            _NEW[k] = True
            return r
        except (TypeError, StreamlitAPIException):
            if _NEW.get(k):
                raise
            _NEW[k] = False
    return fn(*a, use_container_width=True, **kw)


ICON_OK = "icon" in inspect.signature(st.button).parameters

NAV_GROUPS = [
    ("Utama", [("Dashboard", "dashboard")]),
    ("Operasional", [("Data Produk", "inventory_2"), ("Stok & Batch", "warehouse"),
                     ("Transaksi Penjualan", "point_of_sale"), ("Pembelian", "local_shipping")]),
    ("Analitik", [("Harga Jual", "sell"), ("Prediksi & Analitik", "query_stats"),
                  ("Koreksi Prediksi", "edit_note"),
                  ("Risiko Kedaluwarsa", "event_busy"), ("Event Musiman", "calendar_month")]),
    ("Keuangan", [("Laporan Laba", "payments"), ("Biaya Operasional", "receipt_long")]),
    ("Sistem", [("Notifikasi", "notifications")]),
]


def btn(label: str, **kw):
    return wide(st.button, label, **kw)


def submit(label: str, **kw):
    return wide(st.form_submit_button, label, **kw)


# ---------------------------------------------------------------- ikon (gaya garis)
ICONS = {
    "dashboard": "<rect x='3' y='3' width='7' height='9' rx='1.5'/><rect x='14' y='3' width='7' height='5' rx='1.5'/><rect x='14' y='12' width='7' height='9' rx='1.5'/><rect x='3' y='16' width='7' height='5' rx='1.5'/>",
    "produk": "<path d='M21 8 12 3 3 8v8l9 5 9-5z'/><path d='M3 8l9 5 9-5M12 13v8'/>",
    "stok": "<path d='M3 9l9-6 9 6v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z'/><path d='M9 21V12h6v9'/>",
    "penjualan": "<circle cx='9' cy='20.5' r='1'/><circle cx='18' cy='20.5' r='1'/><path d='M2 3h3l2.7 12.4a1 1 0 0 0 1 .8h8.8a1 1 0 0 0 1-.8L20 7H6'/>",
    "pembelian": "<path d='M1 3h13v13H1zM14 8h4l4 4v4h-8z'/><circle cx='5.5' cy='18.5' r='2'/><circle cx='18.5' cy='18.5' r='2'/>",
    "harga": "<path d='M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z'/><circle cx='7' cy='7' r='1'/>",
    "laba": "<path d='M22 7l-8.5 8.5-5-5L2 17'/><path d='M16 7h6v6'/>",
    "prediksi": "<path d='M3 3v18h18'/><path d='M7 14l4-4 4 4 5-6'/>",
    "alert": "<path d='M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'/><path d='M12 9v4M12 17h.01'/>",
    "event": "<rect x='3' y='4' width='18' height='18' rx='2'/><path d='M16 2v4M8 2v4M3 10h18'/>",
    "biaya": "<rect x='2' y='5' width='20' height='14' rx='2'/><path d='M2 10h20'/>",
    "bell": "<path d='M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9'/><path d='M13.7 21a2 2 0 0 1-3.4 0'/>",
    "wallet": "<path d='M20 12V8H6a2 2 0 0 1 0-4h12v4'/><path d='M4 6v12a2 2 0 0 0 2 2h14v-4'/><path d='M18 12a2 2 0 0 0 0 4h4v-4z'/>",
    "trash": "<path d='M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6'/>",
    "layers": "<path d='M12 2l10 5-10 5L2 7z'/><path d='M2 17l10 5 10-5M2 12l10 5 10-5'/>",
    "check": "<path d='M20 6L9 17l-5-5'/>",
    "clock": "<circle cx='12' cy='12' r='10'/><path d='M12 6v6l4 2'/>",
    "cpu": "<rect x='5' y='5' width='14' height='14' rx='2'/><path d='M9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M1 15h4M19 9h4M19 15h4'/>",
}

NAV = [
    ("Dashboard", "dashboard"), ("Data Produk", "produk"), ("Stok & Batch", "stok"),
    ("Transaksi Penjualan", "penjualan"), ("Pembelian", "pembelian"), ("Harga Jual", "harga"),
    ("Laporan Laba", "laba"), ("Prediksi & Analitik", "prediksi"), ("Koreksi Prediksi", "prediksi"),
    ("Risiko Kedaluwarsa", "alert"),
    ("Event Musiman", "event"), ("Biaya Operasional", "biaya"), ("Notifikasi", "bell"),
]


def svg(name: str, size: int = 20) -> str:
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{size}' height='{size}' viewBox='0 0 24 24' fill='none' "
            f"stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{ICONS.get(name, '')}</svg>")


def _nav_css() -> str:
    out = []
    for i, (_, ic) in enumerate(NAV, start=1):
        s = svg(ic, 24).replace("currentColor", "black")
        url = "data:image/svg+xml," + quote(s)
        out.append(
            f'section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type({i})::before'
            f'{{-webkit-mask-image:url("{url}");mask-image:url("{url}");}}'
        )
    return "\n".join(out)


@lru_cache(maxsize=1)
def logo_b64() -> str:
    return base64.b64encode((ASSETS / "logo_bulat.png").read_bytes()).decode()


def load_css() -> None:
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def login_css() -> None:
    st.markdown("<style>.stApp{background:radial-gradient(1200px 600px at 8% 0%,#CDEFFD 0%,transparent 60%),"
                "radial-gradient(900px 500px at 100% 100%,#FFE7C9 0%,transparent 55%),#F2F8FC;}"
                "header[data-testid='stHeader']{display:none}</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------- format
def rp(x) -> str:
    try:
        return "Rp " + f"{float(x):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "-"


def rp_short(x) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "-"
    a = abs(x)
    if a >= 1e9:
        return f"Rp {x/1e9:.2f} M".replace(".", ",")
    if a >= 1e6:
        return f"Rp {x/1e6:.1f} jt".replace(".", ",")
    if a >= 1e3:
        return f"Rp {x/1e3:.0f} rb"
    return f"Rp {x:.0f}"


def num(x) -> str:
    try:
        return f"{float(x):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "-"


# ---------------------------------------------------------------- grafik
def style_fig(fig: go.Figure, height: int = 340, title: str | None = None) -> go.Figure:
    fig.update_layout(template="demandwise", height=height)
    if title:
        fig.update_layout(title=title)
    return fig


def show(fig: go.Figure, height: int = 340, title: str | None = None) -> None:
    wide(st.plotly_chart, style_fig(fig, height, title), config={"displaylogo": False, "responsive": True})


def donut(labels, values, colors, center: str = "", height: int = 300, title: str | None = None) -> go.Figure:
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.68, sort=False,
                           marker=dict(colors=colors, line=dict(color="#fff", width=3)),
                           textinfo="none", hovertemplate="%{label}: %{value} (%{percent})<extra></extra>"))
    if center:
        fig.add_annotation(text=center, showarrow=False, font=dict(size=24, color=NAVY, family="Plus Jakarta Sans"))
    fig.update_layout(legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center"))
    return style_fig(fig, height, title)


# ---------------------------------------------------------------- komponen
def page_header(title: str, subtitle: str = "", chips: list[str] | None = None) -> None:
    ch = "".join(f'<span class="chip">{c}</span>' for c in (chips or []))
    st.markdown(f'<div class="dw-header"><div><h1>{title}</h1><p>{subtitle}</p></div>'
                f'<div class="dw-chips">{ch}</div></div>', unsafe_allow_html=True)


def hero(nama: str, tanggal: str, chips: list[str]) -> None:
    ch = "".join(f'<span class="glass">{c}</span>' for c in chips)
    st.markdown(
        f'<div class="dw-hero"><img src="data:image/png;base64,{logo_b64()}" alt="logo"/>'
        f'<div class="hero-t"><div class="hero-s">Selamat datang kembali</div><h2>{nama}</h2>'
        f'<div class="hero-d">Ringkasan operasional per {tanggal}</div></div>'
        f'<div class="hero-c">{ch}</div></div>', unsafe_allow_html=True)


def section(title: str, hint: str = "") -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    if hint:
        st.markdown(f'<div class="section-hint">{hint}</div>', unsafe_allow_html=True)


def kpi_html(label: str, value: str, delta: str | None = None, tone: str = "blue",
             icon: str = "layers", trend: str = "flat") -> str:
    d = f'<div class="dl {trend}">{delta}</div>' if delta else ""
    return (f'<div class="kpi {tone}"><div class="lb"><span>{label}</span><span class="ic">{svg(icon, 18)}</span></div>'
            f'<div class="vl">{value}</div>{d}</div>')


def kpi_row(items: list[dict]) -> None:
    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        col.markdown(kpi_html(**it), unsafe_allow_html=True)


BADGE_TONE = {
    "menipis": "red", "overstock": "blue", "aman": "green",
    "kritis": "red", "siaga": "orange", "waspada": "yellow", "normal": "green",
    "dipesan": "orange", "dikirim": "blue", "diterima": "green", "draf": "gray",
    "aktif": "green", "habis": "gray", "kedaluwarsa": "red",
    "menunggu": "orange", "disetujui": "green", "ditolak": "red",
    "diskon": "orange", "bundling": "blue", "retur_pemasok": "gray",
    "naik": "green", "turun": "red", "stabil": "gray", "fast": "green", "slow": "gray",
}


def badge(text: str, tone: str | None = None) -> str:
    tone = tone or BADGE_TONE.get(str(text).lower(), "gray")
    return f'<span class="badge b-{tone}">{text}</span>'


_CELL = {
    "red": "background-color:#FEE4E2;color:#B42318;font-weight:700",
    "orange": "background-color:#FFEBD2;color:#B54708;font-weight:700",
    "yellow": "background-color:#FEF6C7;color:#854A0E;font-weight:700",
    "green": "background-color:#D3F8DF;color:#085D3A;font-weight:700",
    "blue": "background-color:#D6EAFF;color:#0B4DA8;font-weight:700",
    "gray": "background-color:#E9EEF3;color:#344054;font-weight:700",
}


def _cell(v):
    tone = BADGE_TONE.get(str(v).lower())
    return _CELL.get(tone, "") if tone else ""


MONEY = {"harga_beli_terakhir", "harga_jual", "hpp", "hpp_satuan", "harga_diskon", "harga_saat_ini",
         "harga_pesaing_rata2", "harga_rekomendasi", "penjualan", "laba_kotor", "laba_bersih", "writeoff",
         "total", "harga", "jumlah_rp"}
PERSEN = {"margin_persen", "perubahan_persen"}
LABEL = {"id": "ID", "produk_id": "ID Produk", "batch_id": "ID Batch", "notif_id": "ID", "nama_produk": "Produk",
         "hpp": "HPP", "hpp_satuan": "HPP / Satuan", "tgl_kedaluwarsa": "Kedaluwarsa", "tgl_masuk": "Tanggal Masuk",
         "tgl_mulai": "Mulai", "tgl_selesai": "Selesai", "sisa_hari": "Sisa Hari", "reorder_point": "Reorder Point",
         "mape": "MAPE", "mae": "MAE", "rmse": "RMSE", "qty_per_hari": "Qty / Hari", "selisih_dari_rop": "Selisih dari ROP",
         "margin_persen": "Margin (%)", "perubahan_persen": "Perubahan (%)", "tunda_pesan": "Tunda Pesan"}


def _label(c: str) -> str:
    if c in LABEL:
        return LABEL[c]
    return c.replace("_", " ").title().replace("Tgl", "Tanggal").replace("Hpp", "HPP").replace("Qty", "Qty")


def _f_rp(v):
    return rp(v) if pd.notna(v) else "-"


def _f_pct(v):
    try:
        return f"{float(v):,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "-"


def _f_num(v):
    try:
        f = float(v)
        t = f"{f:,.0f}" if f.is_integer() else f"{f:,.2f}"
        return t.replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "-"


def tabel(df: pd.DataFrame | None, status_cols: list[str] | None = None, height: int | None = None,
          hide: list[str] | None = None, fmt: dict | None = None, empty: str = "Belum ada data untuk ditampilkan.") -> None:
    """Tabel profesional: header ramah, format rupiah/persen, sel status berwarna."""
    if df is None or len(df) == 0:
        empty_state(empty)
        return
    d = df.copy().reset_index(drop=True)
    if hide:
        d = d.drop(columns=[c for c in hide if c in d.columns])
    formats = {}
    for c in d.columns:
        if c in MONEY:
            formats[c] = _f_rp
        elif c in PERSEN:
            formats[c] = _f_pct
        elif pd.api.types.is_float_dtype(d[c]):
            formats[c] = _f_num
    formats.update({k: v for k, v in (fmt or {}).items() if k in d.columns})
    sty = d.style.format(formats, na_rep="-")
    cols = [c for c in (status_cols or []) if c in d.columns]
    if cols:
        sty = sty.map(_cell, subset=cols)
    cfg = {c: st.column_config.Column(_label(c)) for c in d.columns}
    kw = {"hide_index": True, "column_config": cfg}
    if height:
        kw["height"] = height
    wide(st.dataframe, sty, **kw)


def stepper(steps: list[str], current: str) -> None:
    idx = steps.index(current) if current in steps else -1
    html = '<div class="stepper">'
    for i, s in enumerate(steps):
        cls = "done" if i < idx else ("now" if i == idx else "")
        html += f'<div class="step {cls}">{"✓ " if i < idx else ""}{s.title()}</div>'
    st.markdown(html + "</div>", unsafe_allow_html=True)


def row_card(title: str, sub: str = "", cls: str = "", right: str = "") -> None:
    st.markdown(f'<div class="row-card {cls}"><div class="rc"><div><div class="t">{title}</div>'
                f'<div class="s">{sub}</div></div><div>{right}</div></div></div>', unsafe_allow_html=True)


def notif_card(level: str, judul: str, pesan: str, waktu: str, unread: bool) -> str:
    lv = str(level).lower()
    return (f'<div class="nt {lv} {"unread" if unread else ""}"><div class="nt-h"><span class="nt-t">{judul}</span>'
            f'<span>{badge(lv)}</span></div><div class="nt-m">{pesan}</div><div class="nt-w">{waktu}</div></div>')


def info_card(title: str, body: str, tone: str = "blue") -> None:
    st.markdown(f'<div class="callout {tone}"><div class="ct">{title}</div><div class="cb">{body}</div></div>',
                unsafe_allow_html=True)


def action_card(label: str, value, hint: str, tone: str, icon: str) -> str:
    return (f'<div class="act {tone}"><span class="ic">{svg(icon, 20)}</span><div><div class="av">{value}</div>'
            f'<div class="al">{label}</div><div class="ah">{hint}</div></div></div>')


def empty_state(msg: str, icon: str = "") -> None:
    st.markdown(f'<div class="empty"><div class="ei">{svg("layers", 26)}</div><div>{msg}</div></div>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------- umpan balik
def show_errors(errors: list[str]) -> bool:
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


# ---------------------------------------------------------------- kompatibilitas halaman arsip (pages_asli)
def color_cells(df: pd.DataFrame, cols: list[str]):
    return df.style.map(_cell, subset=cols)


def require_role(*roles: str) -> None:
    user = st.session_state.get("user")
    if not user or (user.get("role") and user["role"] not in roles):
        st.error("Anda tidak memiliki akses ke halaman ini.")
        st.stop()


def current_user() -> dict:
    return st.session_state["user"]
