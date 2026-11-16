"""DemandWise — Smart Inventory & Stock Management.
Entry point: login, routing halaman sesuai role, sidebar dinamis, pusat notifikasi (lonceng)."""
import streamlit as st

from backend import auth_service, notifikasi_service
from backend import mock_data as md
from components import ui

st.set_page_config(page_title="DemandWise", page_icon=str(ui.ASSETS / "icon.png"), layout="wide",
                   initial_sidebar_state="expanded")
ui.load_css()

# key -> (file, judul, ikon, seksi)
HALAMAN = {
    "dashboard": ("pages/dashboard.py", "Dashboard", ":material/dashboard:", "Ringkasan"),
    "prediksi": ("pages/prediksi_stok.py", "Prediksi & Stok", ":material/monitoring:", "Ringkasan"),
    "risiko": ("pages/risiko_kedaluwarsa.py", "Risiko Kedaluwarsa", ":material/event_busy:", "Ringkasan"),
    "g_transaksi": ("pages/gudang_transaksi.py", "Transaksi & Mutasi Stok", ":material/point_of_sale:", "Gudang"),
    "g_opname": ("pages/gudang_opname.py", "Stock Opname", ":material/fact_check:", "Gudang"),
    "g_writeoff": ("pages/gudang_writeoff.py", "Barang Dimusnahkan", ":material/delete_sweep:", "Gudang"),
    "g_tugas": ("pages/gudang_tugas.py", "Tugas Tindak Lanjut", ":material/task_alt:", "Gudang"),
    "m_tindakan": ("pages/manajer_tindakan.py", "Tindakan Batch Berisiko", ":material/rule:", "Manajer"),
    "m_event": ("pages/manajer_event.py", "Event Musiman", ":material/celebration:", "Manajer"),
    "m_biaya": ("pages/manajer_biaya.py", "Biaya Operasional", ":material/receipt_long:", "Manajer"),
    "m_verifikasi": ("pages/manajer_verifikasi.py", "Verifikasi Laporan", ":material/verified:", "Manajer"),
    "p_draf": ("pages/pembelian_draf.py", "Rekomendasi & Draf Pesanan", ":material/shopping_cart:", "Pembelian"),
    "p_alur": ("pages/pesanan_workflow.py", "Alur & Status Pesanan", ":material/local_shipping:", "Pembelian"),
    "h_setuju": ("pages/harga_persetujuan.py", "Persetujuan Harga", ":material/price_check:", "Harga & Laporan"),
    "harga_lap": ("pages/harga_laporan.py", "Harga & Laporan Laba", ":material/payments:", "Harga & Laporan"),
    "analitik": ("pages/analitik.py", "Analitik & Musim", ":material/insights:", "Analitik"),
    "koreksi": ("pages/koreksi_prediksi.py", "Koreksi Prediksi", ":material/edit_note:", "Analitik"),
    "evaluasi": ("pages/evaluasi_model.py", "Evaluasi Model", ":material/model_training:", "Analitik"),
    "notif": ("pages/notifikasi.py", "Pusat Notifikasi", ":material/notifications:", "Lainnya"),
}


def login_view() -> None:
    st.markdown("<div style='height:2vh'></div>", unsafe_allow_html=True)
    left, right = st.columns([1.1, 1], gap="large", vertical_alignment="center")
    with left:
        st.image(str(ui.ASSETS / "logo.png"), width=470)
    with right:
        st.markdown('<div class="login-hero"><h2>Selamat datang di DemandWise</h2>'
                    '<p>Masuk untuk mengelola stok, prediksi, dan profit toko Anda.</p></div>', unsafe_allow_html=True)
        with st.form("login", clear_on_submit=False):
            st.markdown("### Masuk")
            u = st.text_input("Username", placeholder="contoh: manajer")
            p = st.text_input("Password", type="password", placeholder="••••••••")
            go = st.form_submit_button("Masuk", type="primary", width="stretch")
        if go:
            if not u or not p:
                st.error("Username dan password wajib diisi.")
            else:
                user = auth_service.authenticate(u, p)
                if user:
                    st.session_state["user"] = user
                    st.rerun()
                else:
                    st.error("Username atau password salah.")
        with st.expander("Akun demo — klik untuk masuk cepat", expanded=True):
            cols = st.columns(2)
            for i, (uname, d) in enumerate(md.USERS.items()):
                if cols[i % 2].button(f"{d['role']}\n{d['nama']}", key=f"demo_{uname}", width="stretch"):
                    st.session_state["user"] = dict(username=uname, nama=d["nama"], role=d["role"])
                    st.rerun()
            st.caption("Password demo: gudang123 · beli123 · manajer123 · pemilik123")


HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

user = st.session_state.get("user")
if not user:
    st.navigation([st.Page(login_view, title="Masuk", url_path="masuk")], position="hidden").run()
    st.stop()

role = user["role"]
keys = auth_service.AKSES[role]
sections: dict[str, list] = {}
page_objs: dict[str, st.Page] = {}
for k in keys:
    path, title, icon, sec = HALAMAN[k]
    page_objs[k] = st.Page(path, title=title, icon=icon, url_path=k, default=(k == keys[0]))
    sections.setdefault(sec, []).append(page_objs[k])
nav = st.navigation(sections, position="sidebar", expanded=True)

st.logo(str(ui.ASSETS / "logo.png"), size="large", icon_image=str(ui.ASSETS / "icon.png"))

with st.sidebar:
    st.image(str(ui.ASSETS / "logo.png"), width=150)
    st.markdown(f'<div class="user-card"><div class="nm">{user["nama"]}</div><span class="rl">{role}</span></div>',
                unsafe_allow_html=True)
    if st.button("Keluar", icon=":material/logout:", width="stretch"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ---- top bar: tanggal + lonceng notifikasi
top_l, top_r = st.columns([6, 1.3], vertical_alignment="center")
with top_l:
    st.markdown(f'<div class="topbar"><span class="chip">{role}</span> {HARI[md.TODAY.weekday()]}, {md.TODAY.day} {BULAN[md.TODAY.month - 1]} {md.TODAY.year}</div>', unsafe_allow_html=True)
with top_r:
    n = notifikasi_service.jumlah_belum_dibaca(role)
    with st.popover(f"Notifikasi ({n})" if n else "Notifikasi", width="stretch"):
        df = notifikasi_service.get_notifikasi(role).head(6)
        if df.empty:
            st.caption("Tidak ada notifikasi.")
        for r in df.itertuples():
            ui.row_card(f"{'● ' if not r.dibaca else ''}{r.jenis}", f"{r.pesan}<br><span style='font-size:.75rem'>{r.waktu}</span>",
                        "" if r.dibaca else "unread")
        c1, c2 = st.columns(2)
        if c1.button("Tandai dibaca", key="pop_read", width="stretch"):
            notifikasi_service.tandai_semua_dibaca(role)
            st.rerun()
        if "notif" in keys:
            c2.page_link(page_objs["notif"], label="Lihat semua", icon=":material/open_in_new:")

nav.run()
