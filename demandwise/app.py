"""DemandWise - antarmuka Streamlit terintegrasi dengan backend final dan database.

Catatan: berkas ini hanya mengatur TAMPILAN. Seluruh fungsi backend dipanggil dengan nama dan argumen yang sama.
"""
from datetime import date, timedelta
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend.api import (
    login, daftar_akun, get_produk, get_batch, get_notifikasi, tandai_dibaca,
    simpan_penjualan, catat_barang_masuk, catat_retur, catat_barang_rusak,
    catat_writeoff, simpan_opname, tambah_produk, simpan_biaya,
    get_rekomendasi_pembelian, buat_draf_pesanan, setujui_pesanan,
    revisi_pesanan, get_teks_pesanan_wa, simpan_jadwal_kirim, terima_pesanan,
    get_rekomendasi_harga, setujui_harga, ubah_harga_manual,
    get_laporan_laba, get_stok_status, get_risiko_kedaluwarsa,
    get_rekomendasi_tindakan, setujui_tindakan, tolak_tindakan,
    get_event_musiman, simpan_event, get_indeks_musim, get_prediksi,
    jalankan_prediksi, get_evaluasi_model, evaluasi_dan_retrain,
    simpan_koreksi, get_profit_produk, get_tren_produk,
    get_ringkasan_dashboard,
    get_profil, simpan_profil, ganti_password, minta_reset_password, reset_password,
    buat_sesi, cek_sesi, cabut_sesi,
)
import json as _json
import streamlit.components.v1 as _components
from backend.db import get_session
from backend.konteks import KUNCI_SESI, data_sesi, ruang_aktif, ruang_untuk_user
from backend.models import PesananPembelian, DetailPesanan, Pemasok, BiayaOperasional, Produk
from sqlalchemy import select
from components import ui, ekspor

try:  # pembacaan data mentah (hanya baca) untuk membandingkan prediksi model dengan koreksi
    from backend.analitik import data_akses as _da
except Exception:  # pragma: no cover
    _da = None

st.set_page_config(page_title="DemandWise", page_icon=str(ui.ASSETS / "icon.png"), layout="wide")
ui.load_css()

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
MENU = [m for m, _ in ui.NAV]
SUBTITLE = {
    "Dashboard": "Pantau kesehatan bisnis, stok, dan prediksi dalam satu layar.",
    "Data Produk": "Kelola katalog produk, kategori, dan pemasok.",
    "Stok & Batch": "Status stok, batch FEFO, barang masuk, opname, dan penghapusan.",
    "Transaksi Penjualan": "Catat penjualan harian dengan cepat dan akurat.",
    "Pembelian": "Rekomendasi pembelian, draf pesanan, dan penerimaan barang.",
    "Harga Jual": "Rekomendasi harga berbasis HPP, pesaing, dan musim.",
    "Laporan Laba": "Laba rugi periodik: penjualan, HPP, biaya, dan write-off.",
    "Prediksi & Analitik": "Prediksi permintaan, tren, profit produk, dan akurasi model.",
    "Koreksi Prediksi": "Ubah prediksi harian bila Anda tahu faktor yang belum dipahami model. Koreksi ikut dipelajari saat retrain.",
    "Risiko Kedaluwarsa": "Batch berisiko dan rekomendasi tindakan penyelamatan.",
    "Event Musiman": "Kalender event dan indeks musim yang memengaruhi permintaan.",
    "Biaya Operasional": "Catat dan pantau biaya yang membentuk laba bersih.",
    "Notifikasi": "Peringatan stok dan kedaluwarsa yang perlu Anda ketahui.",
    "Profil & Akun": "Profil usaha dan keamanan akun Anda.",
}


def rupiah(v):
    try:
        return "Rp" + f"{float(v):,.0f}".replace(",", ".")
    except Exception:
        return "Rp0"


def tampil_hasil(res, rerun=True):
    """Tampilkan hasil backend. Bila sukses: simpan pesan, bersihkan cache tampilan, muat ulang halaman."""
    if isinstance(res, dict) and res.get("ok"):
        st.cache_data.clear()
        st.session_state["_flash"] = (res.get("pesan", "Berhasil."), res.get("data"))
        if rerun:
            st.rerun()
        else:
            ui.ok(res.get("pesan", "Berhasil."))
    else:
        ui.fail(res.get("pesan", "Proses gagal.") if isinstance(res, dict) else str(res))


def tampil_flash():
    f = st.session_state.pop("_flash", None)
    if f:
        ui.ok(f[0])
        if f[1] is not None:
            with st.expander("Lihat detail hasil proses"):
                st.json(f[1])


def pindah(menu_tujuan):
    st.session_state["menu"] = menu_tujuan


# ---------------------------------------------------------------- sesi login bertahan (cookie)
COOKIE_SESI = "dw_sesi"


def _baca_cookie():
    try:
        return st.context.cookies.get(COOKIE_SESI)
    except Exception:  # streamlit lama tanpa st.context.cookies: sesi tidak bertahan, aplikasi tetap jalan
        return None


def _tulis_cookie(token, hari=0):
    """Tulis (hari > 0) atau hapus (hari = 0) cookie sesi di browser."""
    umur = int(hari) * 86400
    nilai = _json.dumps(token or "")
    _components.html(
        "<script>try{var d=window.parent.document;"
        f"var s=(d.location.protocol==='https:')?'; Secure':'';"
        f"d.cookie='{COOKIE_SESI}='+encodeURIComponent({nilai})+'; Max-Age={umur}; Path=/; SameSite=Lax'+s;"
        "}catch(e){}</script>", height=0)


def _masuk(data, ingat=False):
    """Pasang sesi Streamlit setelah login berhasil (dan cookie bila 'Ingat saya')."""
    st.session_state["user"] = data
    st.session_state[KUNCI_SESI] = data_sesi(ruang_untuk_user(data["user_id"]))
    if ingat:
        r = buat_sesi(data["user_id"])
        if r.get("ok"):
            st.session_state["_dw_token"] = r["data"]["token"]
            st.session_state["_cookie_baru"] = (r["data"]["token"], r["data"]["hari"])


# Cache tampilan dipisah per pemilik data (argumen `_ruang`), supaya hasil akun A tidak terbaca akun B.
@st.cache_data(ttl=300, show_spinner=False)
def _prediksi_cache_ruang(ruang_kunci, pid):
    return get_prediksi(pid)


@st.cache_data(ttl=300, show_spinner=False)
def _profit_cache_ruang(ruang_kunci):
    return get_profit_produk()


def _prediksi_cache(pid):
    return _prediksi_cache_ruang(ruang_aktif().kunci, pid)


def _profit_cache():
    return _profit_cache_ruang(ruang_aktif().kunci)


def ekspor_kanan(df, nama, judul, key, ringkasan=None, teks=None):
    """Baris kecil: keterangan di kiri, tombol Ekspor (CSV / Excel / PDF) di kanan."""
    kiri, kanan = st.columns([5, 1.1], vertical_alignment="center")
    if teks:
        kiri.caption(teks)
    with kanan:
        ekspor.tombol(df, nama, judul, key, ringkasan)


JENIS_NOTIF = {
    "stok_menipis": ("Stok", "Stok & Batch"), "batch_kritis": ("Kedaluwarsa", "Risiko Kedaluwarsa"),
    "batch_siaga": ("Kedaluwarsa", "Risiko Kedaluwarsa"), "batch_waspada": ("Kedaluwarsa", "Risiko Kedaluwarsa"),
    "musim_mendekat": ("Musim", "Event Musiman"), "pesanan_dikirim": ("Pembelian", "Pembelian"),
    "model_diperbarui": ("Model", "Prediksi & Analitik"),
}


def kategori_notif(jenis):
    return JENIS_NOTIF.get(str(jenis), ("Lainnya", None))[0]


def _aman(fn, *a, default=None):
    try:
        return fn(*a)
    except Exception:
        return default


def form_biaya(kunci):
    """Form input biaya operasional dengan validasi sisi layar."""
    with st.form(kunci):
        a, c = st.columns(2)
        t = a.date_input("Tanggal biaya", value=now, max_value=now)
        kat = c.text_input("Kategori biaya", placeholder="Listrik, Sewa Toko, ...")
        e, g = st.columns(2)
        jml = e.number_input("Jumlah (Rp)", min_value=0, step=1000)
        ket = g.text_input("Keterangan")
        simpan = ui.submit("Simpan biaya", type="primary")
    if simpan:
        err = []
        if len(kat.strip()) < 3:
            err.append("Kategori biaya wajib diisi (minimal 3 karakter).")
        if jml <= 0:
            err.append("Jumlah biaya harus lebih dari 0.")
        if not ui.show_errors(err):
            tampil_hasil(simpan_biaya(t, kat.strip(), int(jml), ket))


def _detail_pesanan(pesanan_id):
    """Rincian barang satu pesanan (baca saja)."""
    with get_session() as sesi:
        r = sesi.execute(select(DetailPesanan.produk_id, Produk.nama, Produk.satuan, DetailPesanan.qty_rekomendasi,
                                DetailPesanan.qty_final, DetailPesanan.harga_beli)
                         .join(Produk, Produk.id == DetailPesanan.produk_id)
                         .where(DetailPesanan.pesanan_id == pesanan_id).order_by(Produk.nama)).all()
    d = pd.DataFrame([tuple(x) for x in r], columns=["produk_id", "nama_produk", "satuan", "qty_rekomendasi", "qty_final", "harga_beli"])
    d["qty_rekomendasi"] = pd.to_numeric(d["qty_rekomendasi"], errors="coerce").fillna(0).astype(int)
    d["qty_final"] = pd.to_numeric(d["qty_final"], errors="coerce").fillna(d["qty_rekomendasi"]).astype(int)
    d["harga_beli"] = pd.to_numeric(d["harga_beli"], errors="coerce").fillna(0).astype(float)
    return d


# ====================================================================== LOGIN
def login_view():
    ui.login_css()
    st.markdown("<div style='height:3vh'></div>", unsafe_allow_html=True)
    kiri, kanan = st.columns([1.05, 1], gap="large", vertical_alignment="center")
    with kiri:
        st.markdown(
            f'<div class="lg-panel"><img src="data:image/png;base64,{ui.logo_b64()}" alt="DemandWise"/>'
            '<h2>DemandWise</h2><div class="lg-tag">Predict. Stock. Grow.</div>'
            '<div class="lg-feat"><span>Prediksi permintaan</span><span>Stok FEFO</span>'
            '<span>Rekomendasi harga</span><span>Laba real-time</span></div></div>', unsafe_allow_html=True)
    with kanan:
        # Setelah akun berhasil dibuat, kembali ke tab Masuk (flag dipasang sebelum widget dibuat).
        if st.session_state.pop("_pindah_masuk", False):
            st.session_state["mode_auth"] = "Masuk"
        if st.session_state.pop("_hapus_cookie", False):
            _tulis_cookie("", 0)
        mode = st.radio("Mode", ["Masuk", "Buat akun", "Lupa password"], horizontal=True, key="mode_auth",
                        label_visibility="collapsed")
        if mode == "Masuk":
            st.markdown('<div class="login-hero"><h2>Selamat datang kembali</h2>'
                        '<p>Masuk untuk mengelola stok, pembelian, prediksi, dan profit toko Anda.</p></div>',
                        unsafe_allow_html=True)
            if st.session_state.get("_akun_baru"):
                st.success(st.session_state.pop("_akun_baru"))
            with st.form("login_form"):
                username = st.text_input("Username atau email", placeholder="Masukkan username atau email")
                password = st.text_input("Password", type="password", placeholder="Masukkan password")
                ingat = st.checkbox("Ingat saya di perangkat ini (7 hari)", value=True)
                submit = ui.submit("Masuk ke DemandWise", type="primary")
            if submit and not (username or "").strip():
                st.warning("Username atau email belum diisi.")
            elif submit and not password:
                st.warning("Password belum diisi.")
            elif submit:
                hasil = login(username.strip(), password)
                if hasil.get("ok"):
                    # Ruang data akun ini: akun demo -> data dummy, akun baru -> datanya sendiri.
                    _masuk(hasil["data"], ingat)
                    st.rerun()
                st.error(hasil.get("pesan", "Login gagal."))
            st.caption("Belum punya akun? Pilih **Buat akun** di atas. Lupa password? Pilih **Lupa password**.")
        elif mode == "Lupa password":
            st.markdown('<div class="login-hero"><h2>Lupa password</h2>'
                        '<p>Kami kirim kode 6 angka ke email akun Anda, lalu buat password baru.</p></div>',
                        unsafe_allow_html=True)
            with st.form("lupa_form"):
                email_r = st.text_input("Email akun", placeholder="nama@email.com",
                                        value=st.session_state.get("_reset_email", ""))
                kirim = ui.submit("Kirim kode reset")
            if kirim:
                r = minta_reset_password(email_r)
                if r.get("ok"):
                    st.session_state["_reset_email"] = email_r.strip()
                    st.success(r["pesan"])
                    if (r.get("data") or {}).get("lewat") == "terminal":
                        st.caption("Mode uji: email pengirim belum diatur, kode ditampilkan di terminal aplikasi.")
                else:
                    st.error(r.get("pesan", "Kode belum bisa dikirim."))
            with st.form("reset_form"):
                kode_r = st.text_input("Kode dari email", max_chars=6, placeholder="6 angka")
                r1, r2 = st.columns(2)
                pb1 = r1.text_input("Password baru", type="password", placeholder="Minimal 8 karakter")
                pb2 = r2.text_input("Ulangi password baru", type="password")
                ubah = ui.submit("Simpan password baru", type="primary")
            if ubah:
                r = reset_password(st.session_state.get("_reset_email") or email_r, kode_r, pb1, pb2)
                if r.get("ok"):
                    st.session_state["_akun_baru"] = r["pesan"]
                    st.session_state["_pindah_masuk"] = True
                    st.session_state.pop("_reset_email", None)
                    st.rerun()
                elif r.get("galat"):
                    ui.show_errors(r["galat"])
                else:
                    st.error(r.get("pesan"))
        else:
            st.markdown('<div class="login-hero"><h2>Buat akun baru</h2>'
                        '<p>Daftar dengan email Anda untuk mulai memakai DemandWise.</p></div>',
                        unsafe_allow_html=True)
            with st.form("daftar_form"):
                nama_usaha = st.text_input("Nama usaha", placeholder="Contoh: Toko Berkah Jaya")
                email = st.text_input("Email", placeholder="nama@email.com")
                u_baru = st.text_input("Username", placeholder="4-30 karakter, tanpa spasi")
                c1, c2 = st.columns(2)
                p1 = c1.text_input("Password", type="password", placeholder="Minimal 8 karakter")
                p2 = c2.text_input("Ulangi password", type="password", placeholder="Ketik ulang password")
                st.caption("Password minimal 8 karakter dengan kombinasi huruf dan angka.")
                daftar = ui.submit("Buat akun", type="primary")
            if daftar:
                hasil = daftar_akun(nama_usaha, email, u_baru, p1, p2)
                if hasil.get("ok"):
                    st.session_state["_akun_baru"] = f"Akun untuk {hasil['data']['email']} berhasil dibuat. Silakan masuk."
                    st.session_state["_pindah_masuk"] = True
                    st.rerun()
                elif hasil.get("galat"):
                    ui.show_errors(hasil["galat"])
                else:
                    st.error(hasil.get("pesan", "Gagal membuat akun."))
            st.caption("Sudah punya akun? Pilih **Masuk** di atas.")


if "user" not in st.session_state:
    _tok = _baca_cookie()
    _r = cek_sesi(_tok) if _tok else {"ok": False}
    if _r.get("ok"):   # halaman di-refresh: lanjutkan sesi dari cookie
        st.session_state["user"] = _r["data"]
        st.session_state[KUNCI_SESI] = data_sesi(ruang_untuk_user(_r["data"]["user_id"]))
        st.session_state["_dw_token"] = _tok
    else:
        login_view()
        st.stop()

user = st.session_state["user"]
if KUNCI_SESI not in st.session_state:   # sesi yang login sebelum pembaruan ini
    st.session_state[KUNCI_SESI] = data_sesi(ruang_untuk_user(user["user_id"]))
MODE_DEMO = ruang_aktif().demo
now = date.today()
_PROFIL = (_aman(get_profil, user["user_id"], default={}) or {}).get("data") or {}
if "_cookie_baru" in st.session_state:   # simpan token sesi ke cookie browser setelah login
    _t, _h = st.session_state.pop("_cookie_baru")
    _tulis_cookie(_t, _h)

# ====================================================================== SIDEBAR
_notif = _aman(get_notifikasi, default=pd.DataFrame())
n_unread = int((~_notif["dibaca"].astype(bool)).sum()) if _notif is not None and len(_notif) and "dibaca" in _notif.columns else 0

def nav_item(label, icon, unread=0):
    aktif = st.session_state.get("menu", "Dashboard") == label
    teks = f"{label}  ·  {unread}" if (label == "Notifikasi" and unread) else label
    kw = dict(key=f"nav_{label}", on_click=pindah, args=(label,), type="primary" if aktif else "secondary")
    if ui.ICON_OK:
        kw["icon"] = f":material/{icon}:"
    ui.btn(teks, **kw)


st.session_state.setdefault("menu", "Dashboard")
with st.sidebar:
    st.markdown(
        f'<div class="brand"><img src="data:image/png;base64,{ui.logo_b64()}" alt="logo"/>'
        '<div><div class="bn">DemandWise</div><div class="bt">Predict. Stock. Grow.</div></div></div>',
        unsafe_allow_html=True)
    nama_usaha = user.get("nama_usaha", "Pemilik")
    _avatar = str(nama_usaha)[:1].upper()
    if _PROFIL.get("logo"):
        import base64 as _b64
        _avatar = (f'<img src="data:{_PROFIL.get("logo_tipe") or "image/png"};base64,'
                   f'{_b64.b64encode(_PROFIL["logo"]).decode()}" style="width:100%;height:100%;'
                   'object-fit:cover;border-radius:inherit"/>')
    st.markdown(
        f'<div class="user-card"><div class="av">{_avatar}</div>'
        f'<div><div class="nm">{nama_usaha}</div><div class="rl">'
        f'{"Mode demo · Data presentasi" if MODE_DEMO else "Pemilik · Online"}</div></div></div>',
        unsafe_allow_html=True)
    for grup, items in ui.NAV_GROUPS:
        st.markdown(f'<div class="side-cap">{grup}</div>', unsafe_allow_html=True)
        for label, icon in items:
            nav_item(label, icon, n_unread)
    st.markdown('<div class="side-sep"></div>', unsafe_allow_html=True)
    if ui.btn("Keluar", key="keluar", icon=":material/logout:") if ui.ICON_OK else ui.btn("Keluar", key="keluar"):
        cabut_sesi(st.session_state.get("_dw_token") or _baca_cookie())
        st.session_state.clear()
        st.session_state["_hapus_cookie"] = True
        st.rerun()

menu = st.session_state["menu"]

ui.page_header(menu, SUBTITLE.get(menu, ""),
               [f"{HARI[now.weekday()]}, {now.day} {BULAN[now.month-1]} {now.year}", "Pemilik"])
tampil_flash()

# Akun baru (bukan demo) yang belum mengisi data: tampilkan petunjuk, bukan data contoh.
if not MODE_DEMO and menu not in ("Data Produk", "Profil & Akun"):
    _df_produk = _aman(get_produk, False, default=None)
    _jml_produk = 0 if _df_produk is None else len(_df_produk)
    if _jml_produk == 0:
        st.info("Akun Anda masih kosong. Mulai dengan menambahkan produk di menu **Data Produk**, "
                "lalu catat barang masuk dan penjualan. Halaman ini akan terisi dari data yang Anda masukkan.")
        ui.btn("Buka Data Produk", key="go_produk_kosong", on_click=pindah, args=("Data Produk",))

# ====================================================================== DASHBOARD
if menu == "Dashboard":
    try:
        d = get_ringkasan_dashboard()
        if isinstance(d, dict) and d:
            chips = []
            if d.get("versi_model"):
                vm = str(d["versi_model"])
                chips.append(f"Model {vm}" if vm.lower().startswith("v") else f"Model v{vm}")
            if d.get("mape_terbaru") is not None:
                chips.append(f"MAPE {d['mape_terbaru']}")
            chips.append(f"Periode {d.get('periode_awal', '-')} s/d {d.get('periode_akhir', '-')}")
            ui.hero(user.get("nama_usaha", "Pemilik"), d.get("tanggal_acuan", str(now)), chips)

            jual = d.get("penjualan_30_hari", 0)
            lb = d.get("laba_bersih_30_hari", 0)
            marg = (lb / jual * 100) if jual else 0
            ui.kpi_row([
                dict(label="Penjualan 30 Hari", value=ui.rp_short(jual), delta=rupiah(jual), tone="blue", icon="penjualan"),
                dict(label="Laba Kotor", value=ui.rp_short(d.get("laba_kotor_30_hari", 0)), delta=rupiah(d.get("laba_kotor_30_hari", 0)), tone="cyan", icon="laba"),
                dict(label="Laba Bersih 30 Hari", value=ui.rp_short(lb), delta=f"Margin bersih {marg:.1f}%".replace(".", ","), tone="green", icon="wallet", trend="up" if lb >= 0 else "down"),
                dict(label="Write-off 30 Hari", value=ui.rp_short(d.get("writeoff_30_hari", 0)), delta="Kerugian kedaluwarsa", tone="red", icon="trash", trend="down"),
            ])
            st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
            ui.kpi_row([
                dict(label="Produk Aktif", value=ui.num(d.get("total_produk_aktif", 0)), delta=f"{d.get('produk_fast', 0)} fast · {d.get('produk_slow', 0)} slow", tone="navy", icon="produk"),
                dict(label="Produk Menipis", value=ui.num(d.get("produk_menipis", 0)), delta="Perlu dipesan ulang", tone="orange", icon="stok", trend="down" if d.get("produk_menipis", 0) else "flat"),
                dict(label="Batch Berisiko", value=ui.num(d.get("batch_berisiko", 0)), delta=f"{d.get('batch_kritis', 0)} kritis · {d.get('batch_siaga', 0)} siaga", tone="red", icon="alert"),
                dict(label="Nilai Stok Berisiko", value=ui.rp_short(d.get("nilai_stok_berisiko", 0)), delta="Berdasarkan HPP", tone="orange", icon="clock"),
            ])

            ui.section("Perlu Perhatian", "Klik tombol untuk langsung menuju halaman penanganan.")
            acts = [
                ("Produk menipis", d.get("produk_menipis", 0), "Cek stok & ROP", "orange", "stok", "Stok & Batch"),
                ("Batch perlu tindakan", d.get("batch_perlu_tindakan", 0), "Selamatkan sebelum expired", "red", "alert", "Risiko Kedaluwarsa"),
                ("Rekomendasi menunggu", d.get("rekomendasi_menunggu", 0), "Setujui atau tolak", "blue", "check", "Risiko Kedaluwarsa"),
                ("Notifikasi belum dibaca", d.get("notifikasi_belum_dibaca", 0), "Lihat peringatan terbaru", "green", "bell", "Notifikasi"),
            ]
            for col, (lbl, val, hint, tone, ic, tujuan) in zip(st.columns(4), acts):
                col.markdown(ui.action_card(lbl, val, hint, tone, ic), unsafe_allow_html=True)
                col.button(f"Buka {tujuan}", key=f"go_{lbl}", on_click=pindah, args=(tujuan,))

            ui.section("Analitik Utama")
            c1, c2 = st.columns([1.7, 1], gap="medium")
            with c1:
                pr = _aman(_prediksi_cache, None, default=None)
                if pr is not None and len(pr):
                    pr = pr.copy()
                    pr["tanggal"] = pd.to_datetime(pr["tanggal"])
                    g = pr.groupby("tanggal")[["qty_aktual", "qty_prediksi"]].sum(min_count=1).sort_index()
                    hist = g["qty_aktual"].dropna()
                    prd = g["qty_prediksi"].dropna()
                    if len(hist):
                        prd = prd[prd.index > hist.index.max()] if len(prd) else prd
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=hist.index, y=hist.values, name="Aktual", mode="lines",
                                             line=dict(color=ui.BLUE, width=2.6), fill="tozeroy", fillcolor="rgba(0,87,196,.08)"))
                    fig.add_trace(go.Scatter(x=prd.index, y=prd.values, name="Prediksi", mode="lines",
                                             line=dict(color=ui.ORANGE, width=2.6, dash="dot")))
                    ui.show(fig, 340, "Tren Permintaan Total: Aktual vs Prediksi")
                else:
                    ui.empty_state("Grafik tren akan muncul setelah prediksi tersedia.")
            with c2:
                st_ = [d.get("produk_aman", 0), d.get("produk_menipis", 0), d.get("produk_overstock", 0)]
                ui.show(ui.donut(["Aman", "Menipis", "Overstock"], st_, [ui.GREEN, ui.RED, ui.CYAN],
                                 center=f"{sum(st_)}<br><span style='font-size:11px;color:#5B7088'>produk</span>",
                                 title="Komposisi Status Stok"), 340)

            c3, c4 = st.columns([1.7, 1], gap="medium")
            with c3:
                pf = _aman(_profit_cache, default=None)
                if pf is not None and len(pf):
                    top = pf.sort_values("laba_bersih", ascending=False).head(8).iloc[::-1]
                    fig = go.Figure(go.Bar(x=top["laba_bersih"], y=top["nama_produk"], orientation="h",
                                           marker=dict(color=top["laba_bersih"], colorscale=[[0, ui.CYAN], [1, ui.BLUE]]),
                                           hovertemplate="%{y}<br>Rp %{x:,.0f}<extra></extra>"))
                    ui.show(fig, 340, "8 Produk dengan Laba Bersih Tertinggi")
                else:
                    ui.empty_state("Data profit produk belum tersedia.")
            with c4:
                lv = [d.get("batch_waspada", 0), d.get("batch_siaga", 0), d.get("batch_kritis", 0)]
                fig = go.Figure(go.Bar(x=["Waspada", "Siaga", "Kritis"], y=lv, marker_color=[ui.AMBER, ui.ORANGE, ui.RED],
                                       text=lv, textposition="outside"))
                ui.show(fig, 340, "Batch per Level Risiko")

            c5, c6 = st.columns([1.7, 1], gap="medium")
            with c5:
                ui.section("Status Stok")
                stok = get_stok_status()
                t1, t2 = st.tabs(["Perlu perhatian", "Semua produk"])
                with t1:
                    sub = stok[stok["status"] != "aman"] if len(stok) else stok
                    ui.tabel(sub, status_cols=["status"], height=300, empty="Semua stok dalam kondisi aman.")
                with t2:
                    ui.tabel(stok, status_cols=["status"], height=300)
            with c6:
                ui.section("Notifikasi Terbaru")
                if _notif is not None and len(_notif):
                    for r in _notif[~_notif["dibaca"].astype(bool)].head(4).itertuples():
                        st.markdown(ui.notif_card(r.level, r.judul, r.pesan, str(r.dibuat_pada)[:16], True), unsafe_allow_html=True)
                        st.markdown("<div style='height:.4rem'></div>", unsafe_allow_html=True)
                else:
                    ui.empty_state("Tidak ada notifikasi.")
                mm = d.get("musim_mendekat") or []
                if mm:
                    ui.section("Musim Mendekat")
                    for m in mm[:4]:
                        ui.row_card(m["nama"], f"Mulai {m['tgl_mulai']}", right=ui.badge(f"{m['sisa_hari']} hari", "orange"))
        else:
            st.info("Ringkasan belum tersedia. Pastikan data database sudah terisi.")
    except Exception as e:
        st.error(f"Dashboard belum dapat dimuat: {e}")

# ====================================================================== DATA PRODUK
elif menu == "Data Produk":
    df = get_produk(aktif_saja=False)
    if len(df):
        aktif_n = int(df["aktif"].astype(bool).sum())
        ui.kpi_row([
            dict(label="Total Produk", value=ui.num(len(df)), tone="blue", icon="produk"),
            dict(label="Aktif", value=ui.num(aktif_n), tone="green", icon="check"),
            dict(label="Nonaktif", value=ui.num(len(df) - aktif_n), tone="navy", icon="clock"),
            dict(label="Kategori", value=ui.num(df["kategori"].nunique()), tone="orange", icon="layers"),
        ])
    f1, f2, f3 = st.columns([2, 2, 1.3])
    cari = f1.text_input("Cari produk", placeholder="Ketik nama atau kode produk...")
    kats = sorted(df["kategori"].dropna().unique().tolist()) if len(df) else []
    pilih_kat = f2.multiselect("Kategori", kats, placeholder="Semua kategori")
    status = f3.radio("Status", ["Semua", "Aktif", "Nonaktif"], horizontal=True)
    v = df.copy()
    if len(v):
        if cari:
            m = v["nama_produk"].astype(str).str.contains(cari, case=False, na=False) | v["kode"].astype(str).str.contains(cari, case=False, na=False)
            v = v[m]
        if pilih_kat:
            v = v[v["kategori"].isin(pilih_kat)]
        if status != "Semua":
            v = v[v["aktif"].astype(bool) == (status == "Aktif")]
    st.caption(f"Menampilkan {len(v)} dari {len(df)} produk")
    ui.tabel(v, height=430)
    with st.expander("Tambah produk baru"):
        kat_opts = sorted(df["kategori"].dropna().unique().tolist()) if len(df) else []
        pem_opts = sorted(df["pemasok"].dropna().unique().tolist()) if len(df) else []
        with st.form("add_product"):
            a, b = st.columns(2)
            kode = a.text_input("Kode produk*")
            nama = b.text_input("Nama produk*")
            c, d2 = st.columns(2)
            if MODE_DEMO:  # perilaku lama: pilih kategori/pemasok yang sudah ada
                kategori = c.selectbox("Kategori", kat_opts, index=None, placeholder="Pilih kategori") if kat_opts else c.text_input("Kategori (nama yang sudah ada)")
                pemasok = d2.selectbox("Pemasok", pem_opts, index=None, placeholder="Pilih pemasok") if pem_opts else d2.text_input("Pemasok (nama yang sudah ada)")
            else:          # akun pengguna: boleh pilih yang ada ATAU ketik nama baru (dibuat otomatis)
                kat_pilih = c.selectbox("Kategori", kat_opts, index=None, placeholder="Pilih kategori yang ada") if kat_opts else None
                kat_baru = c.text_input("Kategori baru" if kat_opts else "Kategori*", placeholder="Contoh: Minuman")
                pem_pilih = d2.selectbox("Pemasok", pem_opts, index=None, placeholder="Pilih pemasok yang ada") if pem_opts else None
                pem_baru = d2.text_input("Pemasok baru" if pem_opts else "Pemasok*", placeholder="Contoh: CV Sumber Rejeki")
                kategori = (kat_baru or "").strip() or kat_pilih
                pemasok = (pem_baru or "").strip() or pem_pilih
            e, f = st.columns(2)
            satuan = e.text_input("Satuan*")
            harga_jual = f.number_input("Harga jual*", min_value=0, step=500)
            g, h = st.columns(2)
            hpp = g.number_input("Harga beli terakhir", min_value=0, step=500)
            umur = h.number_input("Umur simpan (hari)", min_value=0, step=1)
            lt = st.number_input("Lead time (hari)", min_value=0, step=1)
            simpan = ui.submit("Simpan produk", type="primary")
        if simpan:
            err, kode_ada = [], set(df["kode"].astype(str).str.lower()) if len(df) else set()
            if not kode.strip():
                err.append("Kode produk wajib diisi.")
            elif kode.strip().lower() in kode_ada:
                err.append(f"Kode '{kode.strip()}' sudah dipakai produk lain.")
            if not nama.strip():
                err.append("Nama produk wajib diisi.")
            if not satuan.strip():
                err.append("Satuan wajib diisi (contoh: pcs, dus, kg).")
            if harga_jual <= 0:
                err.append("Harga jual harus lebih dari 0.")
            if hpp and harga_jual and harga_jual < hpp:
                err.append("Harga jual lebih rendah dari harga beli terakhir. Produk akan dijual rugi.")
            if umur <= 0:
                err.append("Umur simpan wajib diisi (lebih dari 0 hari). Tanpa umur simpan, pesanan tidak bisa diterima menjadi batch.")
            if lt <= 0:
                err.append("Lead time minimal 1 hari agar reorder point dapat dihitung.")
            if not kategori:
                err.append("Pilih kategori produk.")
            if not pemasok:
                err.append("Pilih pemasok produk.")
        if simpan and not ui.show_errors(err):
            tampil_hasil(tambah_produk({"kode": kode, "nama": nama, "kategori": kategori or "", "pemasok": pemasok or "",
                                        "satuan": satuan, "harga_jual": int(harga_jual), "harga_beli_terakhir": int(hpp),
                                        "umur_simpan_hari": int(umur), "lead_time_hari": int(lt)}))

# ====================================================================== STOK & BATCH
elif menu == "Stok & Batch":
    p = get_produk()
    b = get_batch()
    stok = get_stok_status()
    cnt = stok["status"].value_counts() if len(stok) else {}
    ui.kpi_row([
        dict(label="Aman", value=ui.num(cnt.get("aman", 0)), tone="green", icon="check"),
        dict(label="Menipis", value=ui.num(cnt.get("menipis", 0)), tone="red", icon="alert"),
        dict(label="Overstock", value=ui.num(cnt.get("overstock", 0)), tone="cyan", icon="layers"),
        dict(label="Batch Aktif", value=ui.num(len(b)), tone="navy", icon="stok"),
    ])
    t1, t2, t3, t4, t5 = st.tabs(["Status Stok", "Batch Aktif", "Barang Masuk", "Stock Opname", "Rusak · Retur · Write-off"])
    with t1:
        pil = st.radio("Filter status", ["Semua", "menipis", "aman", "overstock"], horizontal=True)
        s = stok if pil == "Semua" else stok[stok["status"] == pil]
        if len(s):
            top = s.head(12).iloc[::-1]
            fig = go.Figure()
            fig.add_trace(go.Bar(y=top["nama_produk"], x=top["stok_saat_ini"], name="Stok saat ini", orientation="h", marker_color=ui.BLUE))
            fig.add_trace(go.Bar(y=top["nama_produk"], x=top["reorder_point"], name="Reorder point", orientation="h", marker_color=ui.ORANGE))
            fig.update_layout(barmode="group")
            ui.show(fig, 420, "Stok vs Reorder Point (12 produk paling kritis)")
        ekspor_kanan(s, "status_stok", "Status Stok", "stok", teks=f"{len(s)} produk")
        ui.tabel(s, status_cols=["status"], height=380)
    with t2:
        if len(b):
            q = st.text_input("Cari batch", placeholder="Nama produk...")
            bv = b[b["nama_produk"].astype(str).str.contains(q, case=False, na=False)] if q else b
            ekspor_kanan(bv.sort_values("tgl_kedaluwarsa"), "batch_aktif", "Batch Aktif (FEFO)", "batch", teks=f"{len(bv)} batch")
            ui.tabel(bv.sort_values("tgl_kedaluwarsa"), status_cols=["status"], height=460)
            st.caption("Diurutkan FEFO: batch yang paling cepat kedaluwarsa di atas.")
        else:
            ui.empty_state("Belum ada batch aktif.")
    opts = {f"{r.nama_produk} (ID {r.produk_id})": int(r.produk_id) for r in p.itertuples()}
    with t3:
        with st.form("barang_masuk"):
            a, c = st.columns(2)
            nama = a.selectbox("Produk", list(opts))
            qty = c.number_input("Jumlah", min_value=1, step=1)
            e, g = st.columns(2)
            exp = e.date_input("Tanggal kedaluwarsa", value=now + timedelta(days=180))
            hpp = g.number_input("HPP satuan (Rp)", min_value=0, step=100)
            simpan = ui.submit("Simpan barang masuk", type="primary")
        if simpan:
            err = []
            if exp <= now:
                err.append("Tanggal kedaluwarsa harus setelah hari ini.")
            if hpp <= 0:
                err.append("HPP satuan harus lebih dari 0 agar laba dihitung benar.")
            if not ui.show_errors(err):
                tampil_hasil(catat_barang_masuk(opts[nama], int(qty), exp, int(hpp), now))
    with t4:
        if not p.empty:
            sis = {int(r.produk_id): int(round(float(r.stok_saat_ini))) for r in stok.itertuples()} if len(stok) else {}
            base = pd.DataFrame({"produk_id": p["produk_id"].astype(int), "Produk": p["nama_produk"],
                                 "Stok sistem": [sis.get(int(i), 0) for i in p["produk_id"]]})
            base["Stok fisik"] = base["Stok sistem"]
            ver = st.session_state.setdefault("_opv", 0)
            st.caption("Kolom Stok fisik sudah terisi sama dengan stok sistem. Ubah hanya produk yang selisih.")
            ed = ui.wide(st.data_editor, base, hide_index=True, key=f"opname_{ver}", height=380,
                         disabled=["produk_id", "Produk", "Stok sistem"],
                         column_config={"produk_id": None, "Stok fisik": st.column_config.NumberColumn(min_value=0, step=1)})
            ed["Stok fisik"] = ed["Stok fisik"].fillna(0).astype(int)
            diff = ed[ed["Stok fisik"] != ed["Stok sistem"]]
            if len(diff):
                ui.info_card(f"{len(diff)} produk berbeda dari stok sistem", ", ".join(diff["Produk"].head(6)) + ("..." if len(diff) > 6 else ""), "orange")
            if ui.btn("Simpan opname", type="primary"):
                items = [{"produk_id": int(i), "stok_fisik": int(f)} for i, f in zip(ed["produk_id"], ed["Stok fisik"])]
                st.session_state["_opv"] = ver + 1
                tampil_hasil(simpan_opname(now, items))
    with t5:
        if not b.empty:
            batch_opts = {f"{r.nama_produk} — batch {r.batch_id} (sisa {r.jumlah_sisa})": r for r in b.itertuples()}
            label = st.selectbox("Pilih batch", list(batch_opts))
            row = batch_opts[label]
            a, c = st.columns([1, 2])
            qty = a.number_input("Jumlah unit", min_value=1, max_value=max(1, int(row.jumlah_sisa)), step=1, key="batch_qty")
            alasan = c.text_input("Keterangan", key="batch_reason", placeholder="Contoh: kemasan sobek / kedaluwarsa")
            x, y, z = st.columns(3)
            with x:
                if ui.btn("Catat rusak"):
                    if len(alasan.strip()) < 3:
                        st.warning("Isi keterangan (minimal 3 karakter) agar kerusakan dapat ditelusuri.")
                    else:
                        tampil_hasil(catat_barang_rusak(int(row.produk_id), int(row.batch_id), int(qty), alasan, now))
            with y:
                if ui.btn("Write-off"):
                    tampil_hasil(catat_writeoff(int(row.batch_id), int(qty), now))
            with z:
                if ui.btn("Retur produk"):
                    if len(alasan.strip()) < 3:
                        st.warning("Isi keterangan (minimal 3 karakter) alasan retur.")
                    else:
                        tampil_hasil(catat_retur(int(row.produk_id), int(qty), alasan, now))
        else:
            ui.empty_state("Belum ada batch aktif.")

# ====================================================================== TRANSAKSI PENJUALAN
elif menu == "Transaksi Penjualan":
    p = get_produk()
    if p.empty:
        st.info("Belum ada produk aktif.")
    else:
        ver = st.session_state.setdefault("_sv", 0)
        kiri, kanan = st.columns([2.1, 1], gap="large")
        with kiri:
            ui.section("Pilih Produk Terjual", "Isi kolom Jumlah. Gunakan ikon pencarian pada tabel untuk menemukan produk.")
            base = pd.DataFrame({"produk_id": p["produk_id"].astype(int), "Produk": p["nama_produk"],
                                 "Satuan": p["satuan"], "Harga": p["harga_jual"].astype(float), "Jumlah": 0})
            ed = ui.wide(st.data_editor, base, hide_index=True, key=f"sale_{ver}", height=520,
                         disabled=["produk_id", "Produk", "Satuan", "Harga"],
                         column_config={"produk_id": None,
                                        "Harga": st.column_config.NumberColumn(format="Rp %d"),
                                        "Jumlah": st.column_config.NumberColumn(min_value=0, step=1)})
        ed["Jumlah"] = ed["Jumlah"].fillna(0).astype(int)
        pilih = ed[ed["Jumlah"] > 0].copy()
        pilih["Subtotal"] = pilih["Jumlah"] * pilih["Harga"]
        with kanan:
            ui.section("Ringkasan Transaksi")
            tgl = st.date_input("Tanggal transaksi", value=now, max_value=now)
            total = float(pilih["Subtotal"].sum()) if len(pilih) else 0
            ui.kpi_row([dict(label="Total", value=ui.rp(total), delta=f"{len(pilih)} produk · {int(pilih['Jumlah'].sum()) if len(pilih) else 0} unit", tone="green", icon="penjualan")])
            if len(pilih):
                for r in pilih.head(8).itertuples():
                    ui.row_card(r.Produk, f"{r.Jumlah} {r.Satuan} × {ui.rp(r.Harga)}", right=f"<b>{ui.rp(r.Subtotal)}</b>")
                if len(pilih) > 8:
                    st.caption(f"+ {len(pilih) - 8} produk lainnya")
            else:
                ui.empty_state("Belum ada produk dipilih.")
            if ui.btn("Simpan penjualan", type="primary"):
                if pilih.empty:
                    st.warning("Masukkan minimal satu jumlah produk.")
                else:
                    items = [{"produk_id": int(i), "qty": int(q)} for i, q in zip(pilih["produk_id"], pilih["Jumlah"])]
                    st.session_state["_sv"] = ver + 1
                    tampil_hasil(simpan_penjualan(tgl, items))

# ====================================================================== PEMBELIAN
elif menu == "Pembelian":
    rek = get_rekomendasi_pembelian()
    with get_session() as s:
        rows = s.execute(select(PesananPembelian.id, PesananPembelian.tanggal, PesananPembelian.status,
                                PesananPembelian.jadwal_kirim, Pemasok.nama)
                         .join(Pemasok, Pemasok.id == PesananPembelian.pemasok_id)
                         .order_by(PesananPembelian.id.desc())).all()
    orders = pd.DataFrame([tuple(r) for r in rows], columns=["pesanan_id", "tanggal", "status", "jadwal_kirim", "pemasok"])
    sc = orders["status"].value_counts() if len(orders) else {}
    ui.kpi_row([
        dict(label="Produk Direkomendasikan", value=ui.num(int((rek["qty_rekomendasi"] > 0).sum()) if len(rek) else 0), tone="blue", icon="produk"),
        dict(label="Draf / Dipesan", value=ui.num(sc.get("draf", 0) + sc.get("dipesan", 0)), delta=f"{sc.get('draf', 0)} draf menunggu persetujuan", tone="orange", icon="clock"),
        dict(label="Dikirim", value=ui.num(sc.get("dikirim", 0)), tone="cyan", icon="pembelian"),
        dict(label="Diterima", value=ui.num(sc.get("diterima", 0)), tone="green", icon="check"),
    ])
    t1, t2, t3 = st.tabs(["Rekomendasi Pembelian", "Daftar Pesanan", "Proses Pesanan"])
    with t1:
        ekspor_kanan(rek, "rekomendasi_pembelian", "Rekomendasi Pembelian", "rekbeli", teks=f"{len(rek)} produk dinilai")
        ui.tabel(rek, height=420)
        if ui.btn("Buat draf pesanan dari rekomendasi", type="primary"):
            tampil_hasil(buat_draf_pesanan())
    with t2:
        st_f = st.radio("Status pesanan", ["Semua", "dipesan", "dikirim", "diterima"], horizontal=True)
        ov = orders if st_f == "Semua" else orders[orders["status"] == st_f]
        st.caption(f"{len(ov)} pesanan")
        ekspor_kanan(ov, "daftar_pesanan", "Daftar Pesanan Pembelian", "pesanan")
        ui.tabel(ov, status_cols=["status"], height=420)
    with t3:
        if orders.empty:
            ui.empty_state("Belum ada pesanan.")
        else:
            info = {int(r.pesanan_id): f"#{r.pesanan_id} · {r.pemasok} · {r.tanggal} · {r.status}" for r in orders.head(300).itertuples()}
            aktif_dulu = [int(i) for i in orders[orders["status"].isin(["draf", "dipesan", "dikirim"])]["pesanan_id"]]
            urut = aktif_dulu + [i for i in info if i not in aktif_dulu]
            pid = st.selectbox("Pilih pesanan (yang perlu diproses di atas)", urut, format_func=lambda i: info.get(i, f"#{i}"))
            baris = orders[orders["pesanan_id"] == pid].iloc[0]
            cur, tgl_pesan, pemasok_nm = str(baris["status"]), baris["tanggal"], baris["pemasok"]
            ui.stepper(["draf", "dipesan", "dikirim", "diterima"], cur)
            det = _detail_pesanan(int(pid))
            tot_qty = int(det["qty_final"].sum()) if len(det) else 0
            tot_nilai = float((det["qty_final"] * det["harga_beli"]).sum()) if len(det) else 0.0
            ui.kpi_row([
                dict(label="Pemasok", value=str(pemasok_nm), tone="navy", icon="produk"),
                dict(label="Jenis Barang", value=ui.num(int((det["qty_final"] > 0).sum()) if len(det) else 0), delta=f"{len(det)} baris di pesanan", tone="blue", icon="layers"),
                dict(label="Total Unit", value=ui.num(tot_qty), tone="cyan", icon="stok"),
                dict(label="Estimasi Nilai", value=ui.rp_short(tot_nilai), delta=ui.rp(tot_nilai), tone="green", icon="wallet"),
            ])
            st.markdown("<div style='height:.4rem'></div>", unsafe_allow_html=True)

            if cur == "draf":
                ui.section("Tinjau & Revisi Jumlah", "Ubah kolom Qty final bila rekomendasi perlu disesuaikan. Isi 0 untuk mengeluarkan barang dari pesanan.")
                ver = st.session_state.setdefault("_rv", 0)
                tampil = det.rename(columns={"nama_produk": "Produk", "satuan": "Satuan", "qty_rekomendasi": "Rekomendasi",
                                             "qty_final": "Qty final", "harga_beli": "Harga beli"})[
                    ["produk_id", "Produk", "Satuan", "Rekomendasi", "Qty final", "Harga beli"]]
                ed = ui.wide(st.data_editor, tampil, hide_index=True, key=f"revisi_{pid}_{ver}", height=min(460, 60 + 36 * len(tampil)),
                             disabled=["produk_id", "Produk", "Satuan", "Rekomendasi", "Harga beli"],
                             column_config={"produk_id": None,
                                            "Harga beli": st.column_config.NumberColumn(format="Rp %d"),
                                            "Qty final": st.column_config.NumberColumn(min_value=0, step=1, required=True)})
                ed["Qty final"] = ed["Qty final"].fillna(0).astype(int)
                berubah = ed[ed["Qty final"] != tampil["Qty final"].astype(int)]
                nilai_baru = float((ed["Qty final"] * ed["Harga beli"]).sum())
                if len(berubah):
                    ui.info_card(f"{len(berubah)} item belum disimpan",
                                 f"Estimasi nilai berubah dari {ui.rp(tot_nilai)} menjadi {ui.rp(nilai_baru)}. Simpan revisi sebelum menyetujui pesanan.", "orange")
                tinggi = ed[ed["Qty final"] > (ed["Rekomendasi"] * 3).clip(lower=10)]
                if len(tinggi):
                    st.warning("Qty final jauh di atas rekomendasi untuk: " + ", ".join(tinggi["Produk"].head(4)) + ". Pastikan tidak terjadi overstock.")
                a, b = st.columns(2)
                with a:
                    if ui.btn("Simpan revisi", key="simpan_revisi", disabled=not len(berubah)):
                        items = [{"produk_id": int(i), "qty_final": int(q)} for i, q in zip(berubah["produk_id"], berubah["Qty final"])]
                        st.session_state["_rv"] = ver + 1
                        tampil_hasil(revisi_pesanan(int(pid), items))
                with b:
                    if ui.btn("Setujui & pesan", type="primary", key="setujui_pesanan", disabled=bool(len(berubah)) or tot_qty == 0,
                              help="Simpan revisi lebih dulu" if len(berubah) else None):
                        tampil_hasil(setujui_pesanan(int(pid)))
                if tot_qty == 0:
                    st.caption("Pesanan kosong tidak dapat disetujui. Naikkan minimal satu Qty final.")
            else:
                ui.section("Rincian Barang")
                ui.tabel(det.drop(columns=["produk_id"]), height=min(380, 60 + 36 * len(det)), fmt={"harga_beli": ui._f_rp})

            if cur == "dipesan":
                ui.section("Jadwal Kirim dari Pemasok", "Catat tanggal pemasok berjanji mengirim. Status pesanan menjadi Dikirim.")
                with st.form(f"jadwal_{pid}"):
                    awal = max(now, tgl_pesan)
                    tgl_kirim = st.date_input("Tanggal kirim", value=awal + timedelta(days=2), min_value=tgl_pesan)
                    kirim = ui.submit("Simpan jadwal kirim", type="primary")
                if kirim:
                    tampil_hasil(simpan_jadwal_kirim(int(pid), tgl_kirim))
            elif cur == "dikirim":
                jk = baris["jadwal_kirim"]
                ui.info_card("Menunggu kedatangan barang", f"Jadwal kirim: {jk if pd.notna(jk) else 'belum dicatat'}. Setelah barang tiba, klik Terima barang agar batch stok dibuat otomatis.", "blue")
                if ui.btn("Terima barang", type="primary", key="terima_pesanan"):
                    tampil_hasil(terima_pesanan(int(pid)))
            elif cur == "diterima":
                ui.info_card("Pesanan selesai", "Barang sudah diterima dan masuk sebagai batch stok.", "green")

            with st.expander("Teks WhatsApp untuk pemasok"):
                st.code(get_teks_pesanan_wa(int(pid)), language=None)
            ekspor_kanan(det.drop(columns=["produk_id"]), f"pesanan_{pid}", f"Pesanan #{pid} - {pemasok_nm}", f"po_{pid}",
                         ringkasan=[("Pemasok", str(pemasok_nm)), ("Tanggal pesanan", str(tgl_pesan)), ("Status", cur),
                                    ("Estimasi nilai", ui.rp(tot_nilai))])

# ====================================================================== HARGA JUAL
elif menu == "Harga Jual":
    df = get_rekomendasi_harga()
    if df.empty:
        ui.empty_state("Belum ada rekomendasi harga.")
    else:
        sk = pd.to_numeric(df["harga_saat_ini"], errors="coerce")
        rk = pd.to_numeric(df["harga_rekomendasi"], errors="coerce")
        naik, turun = int((rk > sk).sum()), int((rk < sk).sum())
        ui.kpi_row([
            dict(label="Total Produk", value=ui.num(len(df)), tone="navy", icon="produk"),
            dict(label="Disarankan Naik", value=ui.num(naik), tone="green", icon="laba", trend="up"),
            dict(label="Disarankan Turun", value=ui.num(turun), tone="red", icon="harga", trend="down"),
            dict(label="Tetap", value=ui.num(len(df) - naik - turun), tone="cyan", icon="check"),
        ])
        hanya = st.toggle("Tampilkan hanya yang direkomendasikan berubah", value=False)
        dv = df[(rk != sk)] if hanya else df
        ekspor_kanan(dv, "rekomendasi_harga", "Rekomendasi Harga Jual", "harga", teks=f"{len(dv)} produk")
        ui.tabel(dv, height=380)
        if "produk_id" in df.columns:
            ui.section("Tinjau & Putuskan")
            nm = {int(r.produk_id): r.nama_produk for r in df.itertuples()}
            pid = st.selectbox("Produk", list(nm), format_func=lambda i: f"{nm[i]} (ID {i})")
            r = df[df["produk_id"] == pid].iloc[0]
            k1, k2 = st.columns([1.3, 1], gap="medium")
            with k1:
                lab = ["HPP", "Harga saat ini", "Rata-rata pesaing", "Rekomendasi"]
                val = [r.get("hpp"), r.get("harga_saat_ini"), r.get("harga_pesaing_rata2"), r.get("harga_rekomendasi")]
                val = [float(v) if pd.notna(v) else 0 for v in val]
                fig = go.Figure(go.Bar(x=lab, y=val, marker_color=[ui.NAVY, ui.BLUE, ui.CYAN, ui.ORANGE], text=[ui.rp(v) for v in val], textposition="outside"))
                ui.show(fig, 330, "Perbandingan Harga")
            with k2:
                ui.info_card("Alasan rekomendasi", str(r.get("alasan", "-")), "orange")
                ui.info_card("Margin & musim", f"Margin: {r.get('margin_persen', '-')}% · Indeks musim: {r.get('indeks_musim', '-')}", "blue")
                if ui.btn("Setujui harga rekomendasi", type="primary"):
                    tampil_hasil(setujui_harga(int(pid)))
                harga_baru = st.number_input("Harga manual (Rp)", min_value=0, step=500)
                hpp_p = float(r.get("hpp")) if pd.notna(r.get("hpp")) else 0.0
                rugi = 0 < harga_baru < hpp_p
                if rugi:
                    st.warning(f"Harga manual di bawah HPP ({ui.rp(hpp_p)}). Setiap unit terjual akan rugi.")
                setuju_rugi = st.checkbox("Saya paham dan tetap ingin menyimpan", key=f"rugi_{pid}") if rugi else True
                if ui.btn("Simpan harga manual"):
                    if harga_baru <= 0:
                        st.warning("Isi harga manual lebih dari 0.")
                    elif not setuju_rugi:
                        st.warning("Centang persetujuan untuk menyimpan harga di bawah HPP.")
                    else:
                        tampil_hasil(ubah_harga_manual(int(pid), int(harga_baru)))

# ====================================================================== LAPORAN LABA
elif menu == "Laporan Laba":
    mode = st.radio("Periode", ["Bulan ini", "30 hari terakhir", "Bulan lalu", "Kustom"], horizontal=True)
    if mode == "Bulan ini":
        awal, akhir = now.replace(day=1), now
    elif mode == "30 hari terakhir":
        awal, akhir = now - timedelta(days=29), now
    elif mode == "Bulan lalu":
        akhir = now.replace(day=1) - timedelta(days=1)
        awal = akhir.replace(day=1)
    else:
        a, b = st.columns(2)
        awal = a.date_input("Dari tanggal", value=now.replace(day=1))
        akhir = b.date_input("Sampai tanggal", value=now)
    st.caption(f"Periode: {awal.strftime('%d/%m/%Y')} – {akhir.strftime('%d/%m/%Y')}")
    t1, t2 = st.tabs(["Ringkasan Laba", "Input Biaya Operasional"])
    with t1:
        if awal <= akhir:
            df = get_laporan_laba(awal, akhir)
            if not df.empty:
                v = {r.komponen: float(r.jumlah) for r in df.itertuples()}
                jual = v.get("Penjualan", 0)
                lbr = v.get("Laba Bersih", 0)
                ui.kpi_row([
                    dict(label="Penjualan", value=ui.rp_short(jual), delta=ui.rp(jual), tone="blue", icon="penjualan"),
                    dict(label="Laba Kotor", value=ui.rp_short(v.get("Laba Kotor", 0)), delta=ui.rp(v.get("Laba Kotor", 0)), tone="cyan", icon="laba"),
                    dict(label="Laba Bersih", value=ui.rp_short(lbr), delta=f"Margin {(lbr / jual * 100 if jual else 0):.1f}%".replace(".", ","), tone="green", icon="wallet", trend="up" if lbr >= 0 else "down"),
                ])
                st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
                ui.kpi_row([
                    dict(label="HPP", value=ui.rp_short(v.get("HPP", 0)), tone="navy", icon="stok"),
                    dict(label="Biaya Operasional", value=ui.rp_short(v.get("Biaya Operasional", 0)), tone="orange", icon="biaya"),
                    dict(label="Write-off", value=ui.rp_short(v.get("Kerugian Kedaluwarsa (Write-off)", 0)), tone="red", icon="trash"),
                ])
                wf = go.Figure(go.Waterfall(
                    x=["Penjualan", "HPP", "Laba Kotor", "Biaya Operasional", "Write-off", "Laba Bersih"],
                    measure=["absolute", "relative", "total", "relative", "relative", "total"],
                    y=[jual, -abs(v.get("HPP", 0)), 0, -abs(v.get("Biaya Operasional", 0)), -abs(v.get("Kerugian Kedaluwarsa (Write-off)", 0)), 0],
                    connector=dict(line=dict(color="#C9DCEB")),
                    increasing=dict(marker=dict(color=ui.BLUE)), decreasing=dict(marker=dict(color=ui.ORANGE)),
                    totals=dict(marker=dict(color=ui.GREEN))))
                ui.show(wf, 380, "Aliran Laba: dari Penjualan ke Laba Bersih")
                ekspor_kanan(df, f"laporan_laba_{awal:%Y%m%d}_{akhir:%Y%m%d}", "Laporan Laba Rugi", "laba",
                             ringkasan=[("Periode", f"{awal:%d/%m/%Y} - {akhir:%d/%m/%Y}"), ("Penjualan", ui.rp(jual)),
                                        ("Laba bersih", ui.rp(lbr)),
                                        ("Margin bersih", f"{(lbr / jual * 100 if jual else 0):.1f}%".replace(".", ","))],
                             teks="Unduh laporan periode ini untuk arsip atau dibagikan.")
                with st.expander("Lihat tabel rincian"):
                    ui.tabel(df, fmt={"jumlah": ui._f_rp})
            else:
                ui.empty_state("Tidak ada data laba pada periode ini.")
        else:
            st.warning("Tanggal awal tidak boleh melewati tanggal akhir.")
    with t2:
        form_biaya("biaya_form")

# ====================================================================== PREDIKSI & ANALITIK
elif menu == "Prediksi & Analitik":
    stok = get_stok_status()
    a, b = st.columns(2)
    with a:
        if ui.btn("Jalankan prediksi stok", type="primary"):
            with st.spinner("Model sedang dijalankan..."):
                tampil_hasil(jalankan_prediksi())
    with b:
        if ui.btn("Evaluasi dan retrain model"):
            with st.spinner("Model sedang dievaluasi..."):
                tampil_hasil(evaluasi_dan_retrain())
    t1, t2, t3, t4, t5 = st.tabs(["Prediksi Produk", "Tren Penjualan", "Profit & Kuadran", "Evaluasi Model", "Koreksi"])
    with t1:
        if len(stok):
            nm = {int(r.produk_id): r.nama_produk for r in stok.itertuples()}
            pid = st.selectbox("Pilih produk", list(nm), format_func=lambda i: nm[i])
            pr = _aman(_prediksi_cache, int(pid), default=None)
            if pr is not None and len(pr):
                pr = pr.copy()
                pr["tanggal"] = pd.to_datetime(pr["tanggal"])
                h = pr[pr["tipe"] == "historis"]
                f = pr[pr["tipe"] == "prediksi"]
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=h["tanggal"], y=h["qty_aktual"], name="Aktual", line=dict(color=ui.BLUE, width=2.6), fill="tozeroy", fillcolor="rgba(0,87,196,.08)"))
                fig.add_trace(go.Scatter(x=f["tanggal"], y=f["qty_prediksi"], name="Prediksi", line=dict(color=ui.ORANGE, width=2.6, dash="dot")))
                ui.show(fig, 380, f"Prediksi Permintaan: {nm[pid]}")
                r = stok[stok["produk_id"] == pid].iloc[0]
                ui.kpi_row([
                    dict(label="Stok Saat Ini", value=ui.num(r["stok_saat_ini"]), tone="blue", icon="stok"),
                    dict(label="Prediksi Lead Time", value=ui.num(r["prediksi_demand_lead_time"]), tone="cyan", icon="prediksi"),
                    dict(label="Reorder Point", value=ui.num(r["reorder_point"]), tone="orange", icon="alert"),
                    dict(label="Status", value=str(r["status"]).title(), tone="green" if r["status"] == "aman" else "red", icon="check"),
                ])
            else:
                ui.empty_state("Belum ada prediksi untuk produk ini. Klik 'Jalankan prediksi stok'.")
    with t2:
        tr = get_tren_produk()
        if len(tr):
            s = tr.sort_values("perubahan_persen")
            ex = pd.concat([s.head(6), s.tail(6)]).drop_duplicates("produk_id")
            fig = go.Figure(go.Bar(x=ex["perubahan_persen"], y=ex["nama_produk"], orientation="h",
                                   marker_color=[ui.GREEN if x >= 0 else ui.RED for x in ex["perubahan_persen"]]))
            ui.show(fig, 420, "Perubahan Penjualan 30 Hari (%): Terendah & Tertinggi")
        ekspor_kanan(tr, "tren_penjualan", "Tren Penjualan Produk", "tren")
        ui.tabel(tr, status_cols=["arah", "kecepatan"], height=380)
    with t3:
        pf = _aman(_profit_cache, default=None)
        if pf is not None and len(pf):
            fig = go.Figure()
            for kq, col in zip(pf["kuadran"].dropna().unique(), ui.COLORWAY):
                sub = pf[pf["kuadran"] == kq]
                fig.add_trace(go.Scatter(x=sub["margin_persen"], y=sub["qty_per_hari"], mode="markers", name=str(kq),
                                         text=sub["nama_produk"], marker=dict(size=14, color=col, opacity=.8, line=dict(color="#fff", width=1.5)),
                                         hovertemplate="%{text}<br>Margin %{x:.1f}%<br>%{y:.1f} unit/hari<extra></extra>"))
            fig.update_xaxes(title="Margin (%)")
            fig.update_yaxes(title="Qty per hari")
            ui.show(fig, 420, "Matriks Margin vs Kecepatan Jual")
        ekspor_kanan(pf, "profit_produk", "Profit per Produk", "profit")
        ui.tabel(pf, status_cols=["kecepatan"], height=380)
    with t4:
        ev_all = get_evaluasi_model(semua_versi=True)
        if ev_all is None or ev_all.empty:
            ui.empty_state("Belum ada evaluasi model. Klik 'Jalankan prediksi stok' atau 'Evaluasi dan retrain model'.")
        else:
            ev_all = ev_all.copy()
            ev_all["dievaluasi_pada"] = pd.to_datetime(ev_all["dievaluasi_pada"], errors="coerce")
            pakai = ev_all[ev_all["dipakai"].astype(bool)]
            riw = (pakai.groupby("versi").agg(dievaluasi_pada=("dievaluasi_pada", "max"), jumlah_produk=("produk_id", "nunique"),
                                              mae=("mae", "mean"), rmse=("rmse", "mean"), mape=("mape", "mean"))
                   .reset_index().sort_values("dievaluasi_pada").reset_index(drop=True))
            terbaru = riw.iloc[-1] if len(riw) else None
            ev = ev_all[ev_all["versi"] == (terbaru["versi"] if terbaru is not None else ev_all.iloc[-1]["versi"])]
            sebelumnya = riw.iloc[-2] if len(riw) > 1 else None
            if terbaru is not None:
                dm = (terbaru["mape"] - sebelumnya["mape"]) if sebelumnya is not None and pd.notna(terbaru["mape"]) and pd.notna(sebelumnya["mape"]) else None
                ui.kpi_row([
                    dict(label="Versi Model Terbaru", value=str(terbaru["versi"]), delta=f"{int(terbaru['jumlah_produk'])} produk dievaluasi", tone="navy", icon="cpu"),
                    dict(label="MAPE Rata-rata", value=("-" if pd.isna(terbaru["mape"]) else f"{terbaru['mape']:.1f}%".replace(".", ",")),
                         delta=("Belum ada pembanding" if dm is None else f"{'Naik' if dm > 0 else 'Turun'} {abs(dm):.1f} poin dari {sebelumnya['versi']}".replace(".", ",")),
                         tone="green" if (dm is None or dm <= 0) else "red", icon="prediksi", trend=None if dm is None else ("down" if dm <= 0 else "up")),
                    dict(label="MAE Rata-rata", value=("-" if pd.isna(terbaru["mae"]) else f"{terbaru['mae']:.2f}".replace(".", ",")), delta="Unit per hari", tone="blue", icon="layers"),
                    dict(label="RMSE Rata-rata", value=("-" if pd.isna(terbaru["rmse"]) else f"{terbaru['rmse']:.2f}".replace(".", ",")), delta=f"{len(riw)} versi tercatat", tone="cyan", icon="layers"),
                ])
            ui.section("Riwayat Retrain", "Setiap kali Evaluasi dan retrain dijalankan, versi baru tercatat di sini. Hanya model terpilih per produk yang dihitung.")
            if len(riw) >= 2:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=riw["versi"], y=riw["mape"], name="MAPE (%)", mode="lines+markers", yaxis="y",
                                         line=dict(color=ui.ORANGE, width=3), marker=dict(size=10)))
                fig.add_trace(go.Bar(x=riw["versi"], y=riw["mae"], name="MAE", yaxis="y2", marker_color=ui.BLUE, opacity=.35))
                fig.update_layout(yaxis=dict(title="MAPE (%)"), yaxis2=dict(title="MAE", overlaying="y", side="right", showgrid=False))
                ui.show(fig, 320, "Akurasi Model per Versi (MAPE makin rendah makin baik)")
            else:
                ui.info_card("Baru satu versi tercatat", "Grafik perbandingan antarversi muncul setelah retrain kedua. Jalankan 'Evaluasi dan retrain model' setelah data penjualan atau koreksi bertambah.", "blue")
            ekspor_kanan(riw, "riwayat_retrain", "Riwayat Retrain Model", "retrain")
            ui.tabel(riw.rename(columns={"jumlah_produk": "produk_dievaluasi"}), height=min(300, 60 + 36 * len(riw)),
                     fmt={"mape": lambda v: "-" if pd.isna(v) else f"{v:.1f}%".replace(".", ","),
                          "mae": lambda v: "-" if pd.isna(v) else f"{v:.2f}".replace(".", ","),
                          "rmse": lambda v: "-" if pd.isna(v) else f"{v:.2f}".replace(".", ",")})

            ui.section("Evaluasi Versi Terbaru", "Perbandingan model kandidat dan produk dengan galat terbesar.")
            c1, c2 = st.columns(2, gap="medium")
            with c1:
                m = ev.groupby("model")[["mae", "rmse"]].mean().reset_index()
                fig = go.Figure()
                fig.add_trace(go.Bar(x=m["model"], y=m["mae"], name="MAE", marker_color=ui.BLUE))
                fig.add_trace(go.Bar(x=m["model"], y=m["rmse"], name="RMSE", marker_color=ui.ORANGE))
                fig.update_layout(barmode="group")
                ui.show(fig, 320, "Rata-rata Galat per Model")
            with c2:
                buruk = ev[ev["dipakai"].astype(bool) & ev["mape"].notna()].sort_values("mape", ascending=False).head(8).iloc[::-1]
                if len(buruk):
                    fig = go.Figure(go.Bar(x=buruk["mape"], y=buruk["nama_produk"], orientation="h", marker_color=ui.RED,
                                           hovertemplate="%{y}<br>MAPE %{x:.1f}%<extra></extra>"))
                    ui.show(fig, 320, "8 Produk dengan MAPE Tertinggi (model terpilih)")
                else:
                    ui.empty_state("MAPE belum bisa dihitung untuk produk mana pun.")
            ekspor_kanan(ev, "evaluasi_model", "Evaluasi Model Versi Terbaru", "evaluasi")
            ui.tabel(ev, height=380)
    with t5:
        st.caption("Koreksi prediksi dikelola di halaman khusus agar lebih leluasa.")
        ui.btn("Buka halaman Koreksi Prediksi", key="go_koreksi", on_click=pindah, args=("Koreksi Prediksi",))

# ====================================================================== KOREKSI PREDIKSI
elif menu == "Koreksi Prediksi":
    stok_k = get_stok_status()
    if stok_k.empty:
        ui.empty_state("Belum ada produk dengan prediksi. Jalankan prediksi stok di halaman Prediksi & Analitik.")
    else:
        nm = {int(r.produk_id): r.nama_produk for r in stok_k.itertuples()}
        pid = st.selectbox("Produk", list(nm), format_func=lambda i: nm[i], key="kor_produk")
        pr = _aman(get_prediksi, int(pid), default=None)
        if pr is None or pr.empty or not (pr["tipe"] == "prediksi").any():
            ui.empty_state("Belum ada prediksi untuk produk ini. Jalankan prediksi stok terlebih dahulu.")
            ui.btn("Ke Prediksi & Analitik", key="go_pred", on_click=pindah, args=("Prediksi & Analitik",))
        else:
            pr = pr.copy()
            pr["tanggal"] = pd.to_datetime(pr["tanggal"])
            hist = pr[pr["tipe"] == "historis"].dropna(subset=["qty_aktual"])
            depan = pr[pr["tipe"] == "prediksi"].sort_values("tanggal").reset_index(drop=True)
            asli = pd.DataFrame(columns=["tanggal", "qty_prediksi"])
            kor_all = pd.DataFrame()
            if _da is not None:
                try:
                    pt = _da.prediksi_tersimpan(terapkan_koreksi=False)
                    asli = pt[pt["produk_id"] == int(pid)][["tanggal", "qty_prediksi"]]
                    kor_all = _da.koreksi_terbaru()
                except Exception:
                    pass
            asli_depan = depan[["tanggal"]].merge(asli, on="tanggal", how="left")["qty_prediksi"].reset_index(drop=True)
            depan["qty_model"] = asli_depan.fillna(depan["qty_prediksi"])
            depan["dikoreksi"] = (depan["qty_prediksi"] - depan["qty_model"]).abs() > 1e-9
            n_kor = int(depan["dikoreksi"].sum())
            ui.kpi_row([
                dict(label="Prediksi Model (total)", value=ui.num(round(float(depan["qty_model"].sum()))), delta=f"{len(depan)} hari ke depan", tone="blue", icon="prediksi"),
                dict(label="Setelah Koreksi (total)", value=ui.num(round(float(depan["qty_prediksi"].sum()))),
                     delta=f"{depan['qty_prediksi'].sum() - depan['qty_model'].sum():+,.0f} unit".replace(",", "."), tone="orange", icon="laba"),
                dict(label="Hari Dikoreksi", value=ui.num(n_kor), delta="Pada produk ini", tone="green", icon="check"),
                dict(label="Rata-rata Harian", value=f"{depan['qty_prediksi'].mean():.1f}".replace(".", ","), delta="Unit per hari (setelah koreksi)", tone="cyan", icon="stok"),
            ])
            c1, c2 = st.columns([1.8, 1], gap="large")
            with c1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=hist["tanggal"], y=hist["qty_aktual"], name="Aktual", line=dict(color=ui.NAVY, width=2)))
                fig.add_trace(go.Scatter(x=depan["tanggal"], y=depan["qty_model"], name="Prediksi model", line=dict(color=ui.ORANGE, width=3, dash="dash")))
                if n_kor:
                    kd = depan[depan["dikoreksi"]]
                    fig.add_trace(go.Scatter(x=kd["tanggal"], y=kd["qty_prediksi"], name="Setelah koreksi", mode="markers+text",
                                             marker=dict(size=12, color=ui.GREEN, symbol="diamond"),
                                             text=kd["qty_prediksi"].round(0), textposition="top center"))
                fig.update_layout(hovermode="x unified", yaxis_title="Unit / hari")
                ui.show(fig, 400, f"{nm[pid]}: prediksi 30 hari dan koreksi")
            with c2:
                ui.section("Input Koreksi")
                with st.form("form_koreksi", clear_on_submit=True):
                    tmin, tmax = depan["tanggal"].min().date(), depan["tanggal"].max().date()
                    tgl = st.date_input("Tanggal yang dikoreksi", value=tmin, min_value=tmin, max_value=tmax)
                    ada = depan[depan["tanggal"] == pd.Timestamp(tgl)]
                    mod = float(ada["qty_model"].iloc[0]) if len(ada) else 0.0
                    st.caption(f"Prediksi model pada tanggal ini: **{mod:.1f} unit**".replace(".", ","))
                    nilai = st.number_input("Nilai koreksi (unit)", min_value=0.0, step=1.0, value=0.0)
                    alasan = st.text_area("Alasan koreksi", placeholder="Contoh: promo toko sebelah, acara sekolah, cuaca ekstrem")
                    yakin = st.checkbox("Saya yakin nilai ini benar meski jauh dari prediksi model")
                    kirim = ui.submit("Simpan koreksi", type="primary")
                if kirim:
                    err = []
                    if nilai <= 0:
                        err.append("Nilai koreksi harus lebih dari 0. Untuk hari toko tutup, tidak perlu dikoreksi.")
                    if len(alasan.strip()) < 8:
                        err.append("Alasan wajib diisi (minimal 8 karakter) agar koreksi bisa ditelusuri.")
                    if mod and nilai > mod * 3 and not yakin:
                        err.append(f"Nilai {nilai:.0f} lebih dari 3x prediksi model ({mod:.0f}). Centang pernyataan yakin bila memang benar.")
                    if not ui.show_errors(err):
                        tampil_hasil(simpan_koreksi(int(pid), tgl, float(nilai), alasan.strip()))
                st.caption("Koreksi langsung tampil di grafik dan dipelajari model saat retrain berikutnya.")
                with st.container():
                    if ui.btn("Retrain model sekarang", key="retrain_kor"):
                        with st.spinner("Model sedang dilatih ulang..."):
                            tampil_hasil(evaluasi_dan_retrain())

            ui.section("Koreksi Aktif", "Koreksi terbaru per produk dan tanggal. Pengubahan nilai dilakukan dengan menyimpan koreksi baru pada tanggal yang sama.")
            if kor_all is not None and len(kor_all):
                namapr = _aman(get_produk, False, default=pd.DataFrame())
                nm_all = dict(zip(namapr["produk_id"], namapr["nama_produk"])) if len(namapr) else {}
                try:
                    pt_all = _da.prediksi_tersimpan(terapkan_koreksi=False)
                except Exception:
                    pt_all = pd.DataFrame(columns=["produk_id", "tanggal", "qty_prediksi"])
                kv = kor_all.merge(pt_all[["produk_id", "tanggal", "qty_prediksi"]], left_on=["produk_id", "tanggal_target"],
                                   right_on=["produk_id", "tanggal"], how="left")
                kv = kv.drop(columns=["tanggal"])
                kv["produk"] = kv["produk_id"].map(nm_all)
                kv["selisih"] = kv["qty_koreksi"] - kv["qty_prediksi"]
                kv = kv.rename(columns={"tanggal_target": "tanggal", "qty_prediksi": "prediksi_model", "qty_koreksi": "koreksi", "dibuat_pada": "dibuat"})
                kv = kv[["produk", "tanggal", "prediksi_model", "koreksi", "selisih", "alasan", "dibuat"]]
                hanya = st.toggle("Hanya produk ini", value=True)
                if hanya:
                    kv = kv[kv["produk"] == nm[pid]]
                kv = kv.sort_values("dibuat", ascending=False)
                ekspor_kanan(kv, "koreksi_prediksi", "Riwayat Koreksi Prediksi", "kor", teks=f"{len(kv)} koreksi")
                ui.tabel(kv, height=min(380, 60 + 36 * max(len(kv), 1)), empty="Belum ada koreksi untuk produk ini.")
            else:
                ui.empty_state("Belum ada koreksi manual.")

# ====================================================================== RISIKO KEDALUWARSA
elif menu == "Risiko Kedaluwarsa":
    risiko = get_risiko_kedaluwarsa()
    tindakan = get_rekomendasi_tindakan()
    menunggu = tindakan[tindakan["status"] == "menunggu"] if len(tindakan) else tindakan
    disetujui = tindakan[tindakan["status"] == "disetujui"] if len(tindakan) else tindakan
    lvc = risiko["level"].value_counts() if len(risiko) else {}
    ui.kpi_row([
        dict(label="Kritis (≤7 hari)", value=ui.num(lvc.get("kritis", 0)), tone="red", icon="alert"),
        dict(label="Siaga (≤14 hari)", value=ui.num(lvc.get("siaga", 0)), tone="orange", icon="clock"),
        dict(label="Waspada (≤30 hari)", value=ui.num(lvc.get("waspada", 0)), tone="navy", icon="bell"),
        dict(label="Rekomendasi Menunggu", value=ui.num(len(menunggu)), delta=f"{len(disetujui)} tugas disetujui", tone="blue", icon="check"),
    ])
    t1, t2, t3 = st.tabs(["Batch Berisiko", "Rekomendasi Tindakan", "Tugas Tindak Lanjut"])
    with t1:
        if len(risiko):
            lv = ["kritis", "siaga", "waspada", "aman"]
            sel = st.multiselect("Level", lv, default=["kritis", "siaga", "waspada"])
            rv = risiko[risiko["level"].isin(sel)] if sel else risiko
            ekspor_kanan(rv, "batch_berisiko", "Batch Berisiko Kedaluwarsa", "risiko", teks=f"{len(rv)} batch")
            ui.tabel(rv, status_cols=["level"], height=420)
        else:
            ui.empty_state("Tidak ada batch berisiko.")
    with t2:
        ui.tabel(menunggu, status_cols=["level", "jenis", "status"], height=300, empty="Tidak ada rekomendasi yang menunggu keputusan.")
        if not menunggu.empty and "id" in menunggu.columns:
            ui.section("Tinjau Rekomendasi")
            info = {int(r.id): f"#{r.id} · {r.nama_produk} · {r.jenis} · {r.level}" for r in menunggu.itertuples()}
            rid = st.selectbox("ID rekomendasi", list(info), format_func=lambda i: info[i])
            r = menunggu[menunggu["id"] == rid].iloc[0]
            ui.info_card(f"{r['nama_produk']} · batch {r['batch_id']}",
                         f"Kedaluwarsa {r['tgl_kedaluwarsa']} (sisa {r['sisa_hari']} hari) · berisiko {r['jumlah_berisiko']} unit · {r['detail']}", "orange")
            a, b = st.columns(2)
            with a:
                if ui.btn("Setujui tindakan", type="primary"):
                    tampil_hasil(setujui_tindakan(int(rid)))
            with b:
                if ui.btn("Tolak tindakan"):
                    tampil_hasil(tolak_tindakan(int(rid)))
            with st.expander("Tetapkan tindakan lain"):
                st.caption("Gunakan bila rekomendasi sistem tidak cocok dan Anda punya rencana sendiri. Rencana dicatat dan rekomendasi ditutup.")
                lain = st.text_area("Tindakan yang akan dilakukan", key=f"lain_{rid}", placeholder="Contoh: tukar ke toko cabang, donasi, kirim promo ke pelanggan tetap")
                if ui.btn("Simpan tindakan lain", key=f"simpan_lain_{rid}"):
                    if len(lain.strip()) < 5:
                        st.warning("Jelaskan tindakan lain minimal 5 karakter.")
                    else:
                        tampil_hasil(tolak_tindakan(int(rid), lain.strip()))
    with t3:
        ui.section("Daftar Tugas Gudang", "Dibuat otomatis dari rekomendasi yang sudah Anda setujui, diurutkan dari yang paling mendesak.")
        if disetujui.empty:
            ui.empty_state("Belum ada tugas. Tugas muncul setelah Anda menyetujui rekomendasi tindakan.")
        else:
            tugas = disetujui.sort_values("sisa_hari").copy()
            tugas["stok_batch"] = pd.to_numeric(tugas["stok_batch"], errors="coerce").fillna(0)
            selesai = tugas[tugas["stok_batch"] <= 0]
            buka = tugas[tugas["stok_batch"] > 0]
            ui.kpi_row([
                dict(label="Tugas Terbuka", value=ui.num(len(buka)), tone="orange", icon="clock"),
                dict(label="Mendesak (≤7 hari)", value=ui.num(int((buka["sisa_hari"] <= 7).sum())), tone="red", icon="alert"),
                dict(label="Selesai (stok batch habis)", value=ui.num(len(selesai)), tone="green", icon="check"),
            ])
            LANGKAH = {"diskon": "Pasang harga diskon", "retur_pemasok": "Ajukan retur ke pemasok", "bundling": "Buat paket bundling",
                       "lainnya": "Tarik dari rak dan catat write-off"}
            if len(buka):
                for t in buka.itertuples():
                    tone = "red" if t.sisa_hari <= 7 else ("orange" if t.sisa_hari <= 14 else "blue")
                    harga = f" · harga diskon {ui.rp(t.harga_diskon)}" if pd.notna(t.harga_diskon) and t.jenis in ("diskon", "bundling", "retur_pemasok") else ""
                    ui.row_card(f"{LANGKAH.get(t.jenis, str(t.jenis).title())}: {t.nama_produk}",
                                f"Batch {t.batch_id} · {int(t.stok_batch)} unit tersisa · kedaluwarsa {str(t.tgl_kedaluwarsa)[:10]} (sisa {int(t.sisa_hari)} hari){harga}<br>{t.detail}",
                                right=ui.badge(f"{int(t.sisa_hari)} hari", tone))
            else:
                ui.empty_state("Semua tugas selesai.")
            ekspor_kanan(tugas[["nama_produk", "batch_id", "jenis", "tgl_kedaluwarsa", "sisa_hari", "stok_batch", "harga_diskon", "detail"]],
                         "tugas_tindak_lanjut", "Tugas Tindak Lanjut Gudang", "tugas")
            st.caption("Tugas dianggap selesai bila stok batch sudah habis (terjual, diretur, atau di-write-off). Pencatatan dilakukan di Stok & Batch.")
        riwayat = tindakan[tindakan["status"].isin(["ditolak", "tindakan_lain"])] if len(tindakan) else tindakan
        if len(riwayat):
            with st.expander(f"Riwayat keputusan lain ({len(riwayat)})"):
                ui.tabel(riwayat[["nama_produk", "batch_id", "jenis", "status", "detail", "dibuat_pada"]], status_cols=["status"], height=260)

# ====================================================================== EVENT MUSIMAN
elif menu == "Event Musiman":
    ev = get_event_musiman()
    idx = get_indeks_musim()
    t1, t2, t3 = st.tabs(["Kalender Event", "Indeks Musim", "Tambah Event"])
    with t1:
        if len(ev):
            e = ev.copy()
            e["tgl_mulai"] = pd.to_datetime(e["tgl_mulai"])
            e["tgl_selesai"] = pd.to_datetime(e["tgl_selesai"])
            e["dur"] = (e["tgl_selesai"] - e["tgl_mulai"]).dt.total_seconds() * 1000 + 86400000
            fig = go.Figure(go.Bar(y=e["nama"], x=e["dur"], base=e["tgl_mulai"], orientation="h", marker_color=ui.BLUE,
                                   hovertemplate="%{y}<extra></extra>"))
            fig.update_xaxes(type="date")
            fig.update_yaxes(autorange="reversed")
            ui.show(fig, max(320, 30 * len(e) + 100), "Linimasa Event Musiman")
        ui.tabel(ev, height=320)
    with t2:
        if len(idx):
            tampilan = st.radio("Tampilan", ["Heatmap per produk", "Rata-rata per bulan"], horizontal=True, key="mode_idx")
            if tampilan == "Heatmap per produk":
                f1, f2, f3 = st.columns([2, 1.2, 1.4])
                cari = f1.text_input("Cari produk", key="idx_cari", placeholder="Ketik nama produk...")
                urut = f2.selectbox("Urutkan", ["Paling musiman", "Indeks puncak tertinggi", "Nama A-Z"], key="idx_urut")
                maks = f3.slider("Jumlah produk", 5, max(10, min(60, idx["produk_id"].nunique())), 20, key="idx_n")
                iv = idx.copy()
                if cari:
                    iv = iv[iv["nama_produk"].astype(str).str.contains(cari, case=False, na=False)]
                pv = iv.pivot_table(index="nama_produk", columns="bulan", values="indeks", aggfunc="mean").reindex(columns=range(1, 13))
                if pv.empty:
                    ui.empty_state("Tidak ada produk yang cocok dengan pencarian.")
                else:
                    if urut == "Paling musiman":
                        pv = pv.loc[(pv.max(axis=1) - pv.min(axis=1)).sort_values(ascending=False).index]
                    elif urut == "Indeks puncak tertinggi":
                        pv = pv.loc[pv.max(axis=1).sort_values(ascending=False).index]
                    else:
                        pv = pv.sort_index()
                    pv = pv.head(maks)
                    ev_bulan = idx.groupby("bulan")["event_terkait"].first().to_dict() if "event_terkait" in idx.columns else {}
                    hover = [[(ev_bulan.get(m) or "-") for m in pv.columns] for _ in pv.index]
                    zmax = float(max(1.5, pv.max().max())) if pv.notna().any().any() else 2.0
                    zmin = float(min(0.5, pv.min().min())) if pv.notna().any().any() else 0.5
                    fig = go.Figure(go.Heatmap(
                        z=pv.values, x=[BULAN[m - 1][:3] for m in pv.columns], y=list(pv.index), customdata=hover,
                        colorscale=[[0, ui.CYAN], [(1 - zmin) / (zmax - zmin), "#FFFFFF"], [1, ui.ORANGE]],
                        zmin=zmin, zmax=zmax, xgap=2, ygap=2, colorbar=dict(title="Indeks"),
                        text=[[("" if pd.isna(v) else f"{v:.2f}".replace(".", ",")) for v in row] for row in pv.values] if len(pv) <= 25 else None,
                        texttemplate="%{text}" if len(pv) <= 25 else None, textfont=dict(size=11),
                        hovertemplate="%{y}<br>%{x}: indeks %{z:.2f}<br>Event: %{customdata}<extra></extra>"))
                    fig.update_yaxes(autorange="reversed")
                    fig.update_xaxes(side="top")
                    ui.show(fig, max(360, 28 * len(pv) + 140), "Heatmap Indeks Musim (1,0 = normal · oranye = laris · biru = sepi)")
                    ringkas = pd.DataFrame({"bulan": [BULAN[m - 1] for m in range(1, 13)],
                                            "indeks_rata2": [idx[idx["bulan"] == m]["indeks"].mean() for m in range(1, 13)],
                                            "event_terkait": [ev_bulan.get(m) or "-" for m in range(1, 13)]})
                    with st.expander("Ringkasan per bulan dan event terkait"):
                        ui.tabel(ringkas, height=300, fmt={"indeks_rata2": lambda v: "-" if pd.isna(v) else f"{v:.2f}".replace(".", ",")})
            else:
                rata = idx.groupby("bulan")["indeks"].mean().reset_index()
                rata["nama"] = rata["bulan"].astype(int).map(lambda m: BULAN[m - 1][:3])
                fig = go.Figure(go.Scatter(x=rata["nama"], y=rata["indeks"], mode="lines+markers", line=dict(color=ui.BLUE, width=3, shape="spline"),
                                           marker=dict(size=9, color=ui.ORANGE), fill="tozeroy", fillcolor="rgba(0,87,196,.08)"))
                fig.add_hline(y=1, line_dash="dot", line_color=ui.MUTED)
                ui.show(fig, 320, "Rata-rata Indeks Musim per Bulan (1,0 = normal)")
            ekspor_kanan(idx, "indeks_musim", "Indeks Musim per Produk dan Bulan", "idxmusim")
            ui.tabel(idx, height=340)
        else:
            ui.empty_state("Indeks musim belum tersedia.")
    with t3:
        with st.form("event_form"):
            nama = st.text_input("Nama event")
            a, c = st.columns(2)
            mulai = a.date_input("Tanggal mulai", value=now + timedelta(days=30))
            selesai = c.date_input("Tanggal selesai", value=now + timedelta(days=37))
            simpan = ui.submit("Tambah event", type="primary")
        if simpan:
            err = []
            if len(nama.strip()) < 3:
                err.append("Nama event wajib diisi (minimal 3 karakter).")
            if selesai < mulai:
                err.append("Tanggal selesai tidak boleh sebelum tanggal mulai.")
            if (selesai - mulai).days > 60:
                err.append("Durasi event lebih dari 60 hari. Pecah menjadi beberapa event agar indeks musim akurat.")
            if len(ev) and ((ev["nama"].astype(str).str.lower() == nama.strip().lower()) & (pd.to_datetime(ev["tgl_mulai"]).dt.date == mulai)).any():
                err.append("Event dengan nama dan tanggal mulai yang sama sudah ada.")
            if not ui.show_errors(err):
                tampil_hasil(simpan_event(nama.strip(), mulai, selesai))

# ====================================================================== BIAYA OPERASIONAL
elif menu == "Biaya Operasional":
    ui.info_card("Biaya masuk ke perhitungan laba", "Setiap biaya yang disimpan otomatis dipakai pada Laporan Laba untuk menghitung laba bersih.", "blue")
    with get_session() as s:
        rows = s.execute(select(BiayaOperasional.tanggal, BiayaOperasional.kategori_biaya, BiayaOperasional.jumlah,
                                BiayaOperasional.keterangan).order_by(BiayaOperasional.tanggal.desc()).limit(500)).all()
    bd = pd.DataFrame(rows, columns=["tanggal", "kategori_biaya", "jumlah", "keterangan"])
    t1, t2 = st.tabs(["Riwayat & Ringkasan", "Input Biaya"])
    with t1:
        if len(bd):
            k = bd.groupby("kategori_biaya")["jumlah"].sum().sort_values(ascending=False)
            c1, c2 = st.columns([1, 1.4], gap="medium")
            with c1:
                ui.show(ui.donut(list(k.index), list(k.values), ui.COLORWAY, center=ui.rp_short(k.sum()), title="Komposisi Biaya (500 catatan terbaru)"), 360)
            with c2:
                ui.tabel(bd, fmt={"jumlah": ui._f_rp}, height=360)
        else:
            ui.empty_state("Belum ada catatan biaya.")
    with t2:
        form_biaya("biaya_form_page")

# ====================================================================== NOTIFIKASI
elif menu == "Notifikasi":
    df = get_notifikasi()
    if df.empty or "notif_id" not in df.columns:
        ui.empty_state("Tidak ada notifikasi.")
    else:
        unread = df[~df["dibaca"].astype(bool)]
        ui.kpi_row([
            dict(label="Belum Dibaca", value=ui.num(len(unread)), tone="orange", icon="bell"),
            dict(label="Kritis", value=ui.num((df["level"] == "kritis").sum()), tone="red", icon="alert"),
            dict(label="Siaga", value=ui.num((df["level"] == "siaga").sum()), tone="orange", icon="clock"),
            dict(label="Total", value=ui.num(len(df)), tone="navy", icon="layers"),
        ])
        df = df.assign(kategori=df["jenis"].map(kategori_notif))
        f1, f2 = st.columns([3, 1])
        flt = f1.radio("Tampilkan", ["Semua", "Belum dibaca", "kritis", "siaga", "waspada"], horizontal=True)
        with f2:
            if len(unread) and ui.btn("Tandai semua dibaca", type="primary"):
                for nid in unread["notif_id"].astype(int):
                    tandai_dibaca(int(nid))
                tampil_hasil({"ok": True, "pesan": f"{len(unread)} notifikasi ditandai sudah dibaca."})
        kats = sorted(df["kategori"].unique().tolist())
        g1, g2 = st.columns([2, 1.4])
        pilih_k = g1.multiselect("Kategori", kats, default=kats, placeholder="Semua kategori")
        kata = g2.text_input("Cari", placeholder="Nama produk atau kata kunci...", key="nt_cari")
        hitung = df[~df["dibaca"].astype(bool)]["kategori"].value_counts()
        if len(hitung):
            st.caption("Belum dibaca per kategori: " + " · ".join(f"{k} {int(n)}" for k, n in hitung.items()))
        v = df[df["kategori"].isin(pilih_k)] if pilih_k else df
        if flt == "Belum dibaca":
            v = v[~v["dibaca"].astype(bool)]
        elif flt in ("kritis", "siaga", "waspada"):
            v = v[v["level"] == flt]
        if kata:
            v = v[v["judul"].astype(str).str.contains(kata, case=False, na=False) | v["pesan"].astype(str).str.contains(kata, case=False, na=False)]
        v = v.assign(_u=v["dibaca"].astype(bool)).sort_values(["_u", "dibuat_pada"], ascending=[True, False]).head(60)
        if v.empty:
            ui.empty_state("Tidak ada notifikasi yang cocok dengan filter.")
        for r in v.itertuples():
            c1, c2 = st.columns([6, 1.4], vertical_alignment="center")
            c1.markdown(ui.notif_card(r.level, f"{r.judul}", r.pesan, f"{str(r.dibuat_pada)[:16]} · {r.kategori}", not bool(r.dibaca)), unsafe_allow_html=True)
            with c2:
                tujuan = JENIS_NOTIF.get(str(r.jenis), (None, None))[1]
                if tujuan:
                    ui.btn("Buka halaman", key=f"nb_{int(r.notif_id)}", on_click=pindah, args=(tujuan,))
                if not bool(r.dibaca):
                    if ui.btn("Tandai dibaca", key=f"nt_{int(r.notif_id)}"):
                        tampil_hasil(tandai_dibaca(int(r.notif_id)))

# ====================================================================== PROFIL & AKUN
elif menu == "Profil & Akun":
    pr = _PROFIL
    if MODE_DEMO:
        st.info("Ini akun demo untuk presentasi. Profil dan password akun demo dikunci agar login "
                "dan data presentasi tetap utuh. Buat akun baru untuk mencoba fitur ini.")
    t1, t2 = st.tabs(["Profil Usaha", "Keamanan Akun"])
    with t1:
        if not MODE_DEMO and not pr.get("terisi"):
            st.caption("Profil belum diisi. Isi bagian yang Anda perlukan saja; sisanya bisa dilengkapi kapan pun.")
        elif pr.get("diubah_pada"):
            st.caption(f"Terakhir diperbarui {str(pr['diubah_pada'])[:16]}")
        kiri, kanan = st.columns([2.2, 1], gap="large")
        with kiri:
            with st.form("form_profil"):
                a1, a2 = st.columns(2)
                p_nama = a1.text_input("Nama usaha*", value=pr.get("nama_usaha") or user.get("nama_usaha", ""), disabled=MODE_DEMO)
                p_jenis = a2.text_input("Jenis usaha", value=pr.get("jenis_usaha") or "", placeholder="Contoh: Toko kelontong", disabled=MODE_DEMO)
                b1, b2 = st.columns(2)
                p_pemilik = b1.text_input("Nama pemilik", value=pr.get("nama_pemilik") or "", disabled=MODE_DEMO)
                p_telp = b2.text_input("Telepon / WhatsApp", value=pr.get("telepon") or "", placeholder="0812-3456-7890", disabled=MODE_DEMO)
                p_alamat = st.text_area("Alamat", value=pr.get("alamat") or "", height=80, disabled=MODE_DEMO)
                p_kota = st.text_input("Kota / kabupaten", value=pr.get("kota") or "", disabled=MODE_DEMO)
                p_logo = st.file_uploader("Logo usaha (PNG/JPG, maks 1 MB)", type=["png", "jpg", "jpeg"], disabled=MODE_DEMO)
                p_hapus = st.checkbox("Hapus logo saat ini", disabled=MODE_DEMO or not pr.get("logo"))
                simpan_p = ui.submit("Simpan profil", type="primary", disabled=MODE_DEMO)
            if simpan_p:
                data = {"nama_usaha": p_nama, "jenis_usaha": p_jenis, "nama_pemilik": p_pemilik,
                        "telepon": p_telp, "alamat": p_alamat, "kota": p_kota, "hapus_logo": p_hapus}
                if p_logo is not None:
                    data["logo"] = p_logo.getvalue()
                    data["logo_tipe"] = "image/png" if p_logo.name.lower().endswith(".png") else "image/jpeg"
                r = simpan_profil(user["user_id"], data)
                if r.get("ok"):
                    st.session_state["user"]["nama_usaha"] = r["data"]["nama_usaha"]
                    tampil_hasil(r)
                elif r.get("galat"):
                    ui.show_errors(r["galat"])
                else:
                    ui.fail(r.get("pesan", "Profil belum tersimpan."))
        with kanan:
            st.markdown("**Akun**")
            st.caption(f"Username: {pr.get('username') or '-'}")
            st.caption(f"Email: {pr.get('email') or '-'}")
            st.caption("Jenis akun: " + ("Demo (data presentasi)" if MODE_DEMO else "Pengguna"))
            if pr.get("logo"):
                st.image(pr["logo"], caption="Logo usaha", width=160)
    with t2:
        st.markdown("**Ganti password**")
        with st.form("form_password"):
            g0 = st.text_input("Password lama", type="password", disabled=MODE_DEMO)
            g1, g2 = st.columns(2)
            gb1 = g1.text_input("Password baru", type="password", placeholder="Minimal 8 karakter, huruf & angka", disabled=MODE_DEMO)
            gb2 = g2.text_input("Ulangi password baru", type="password", disabled=MODE_DEMO)
            ganti = ui.submit("Ganti password", type="primary", disabled=MODE_DEMO)
        if ganti:
            r = ganti_password(user["user_id"], g0, gb1, gb2, st.session_state.get("_dw_token"))
            if r.get("ok"):
                tampil_hasil(r)
            elif r.get("galat"):
                ui.show_errors(r["galat"])
            else:
                ui.fail(r.get("pesan"))
        st.caption("Setelah password diganti, login di perangkat lain otomatis keluar. "
                   "Pilihan \"Ingat saya\" menyimpan login di perangkat ini selama 7 hari; tombol Keluar mengakhirinya.")

st.markdown('<div class="foot">DemandWise · Predict. Stock. Grow.</div>', unsafe_allow_html=True)
