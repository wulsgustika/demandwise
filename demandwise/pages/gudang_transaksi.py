"""Staf Gudang: transaksi penjualan, barang masuk, retur, barang rusak, input batch."""
from datetime import timedelta

import pandas as pd
import streamlit as st

from backend import mock_data as md
from backend import stok_service
from components import ui

ui.require_role("Staf Gudang", "Manajer")
user = ui.current_user()
ui.page_header("Transaksi & Mutasi Stok", "Catat penjualan (stok berkurang otomatis FEFO), barang masuk, retur, barang rusak, dan batch.")

prod = stok_service.get_produk()
stok = stok_service.get_stok()
by_name = prod.set_index("nama")
nama_list = prod.nama.tolist()
batch = stok_service.get_batch()

tabs = st.tabs(["Penjualan", "Barang Masuk", "Retur", "Barang Rusak", "Input Batch"])

# ---------------------------------------------------------------- Penjualan
with tabs[0]:
    c1, c2 = st.columns([1.5, 1], gap="large")
    with c1:
        ui.section("Keranjang transaksi", "Pilih produk & jumlah. Tambah baris dengan klik baris kosong di bawah tabel.")
        cart = st.data_editor(
            pd.DataFrame({"Produk": [nama_list[0]], "Qty": [1]}), num_rows="dynamic", width="stretch", key="cart",
            column_config={"Produk": st.column_config.SelectboxColumn("Produk", options=nama_list, required=True, width="large"),
                           "Qty": st.column_config.NumberColumn("Qty", min_value=1, step=1, default=1, required=True)},
        )
        metode = st.radio("Metode pembayaran", ["Tunai", "QRIS", "Transfer", "Debit"], horizontal=True)
    cart = cart.dropna(subset=["Produk"]) if len(cart) else cart
    rows, total = [], 0.0
    for r in cart.itertuples():
        p = by_name.loc[r.Produk]
        q = int(r.Qty or 0)
        sub = q * float(p.harga)
        total += sub
        rows.append(dict(Produk=r.Produk, Qty=q, Harga=ui.rp(p.harga), Subtotal=ui.rp(sub), Stok=int(stok[p.produk_id]),
                         Status="OK" if q <= stok[p.produk_id] else "Stok kurang"))
    with c2:
        ui.section("Ringkasan")
        st.markdown(ui.kpi_html("Total belanja", ui.rp(total), f"{len(rows)} item", "blue"), unsafe_allow_html=True)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if st.button("Simpan Transaksi", type="primary", key="btn_jual"):
        err = []
        if not rows:
            err.append("Keranjang masih kosong.")
        if any(r["Qty"] <= 0 for r in rows):
            err.append("Qty setiap item harus lebih dari 0.")
        if any(r["Status"] != "OK" for r in rows):
            err.append("Ada item yang jumlahnya melebihi stok tersedia.")
        if len({r["Produk"] for r in rows}) != len(rows):
            err.append("Produk yang sama muncul lebih dari sekali. Gabungkan jumlahnya.")
        if not ui.show_errors(err):
            res = stok_service.simpan_penjualan([dict(produk_id=int(by_name.loc[r["Produk"]].produk_id), qty=r["Qty"]) for r in rows], metode, user["nama"])
            if res["ok"]:
                ui.ok(f"{res['pesan']} Total {ui.rp(res['total'])}")
                st.markdown("**Batch yang dikurangi (FEFO):**")
                st.dataframe(pd.DataFrame(res["rincian"]).rename(columns={"produk": "Produk", "batch_id": "Batch", "tgl_exp": "Kedaluwarsa", "diambil": "Diambil"}),
                             hide_index=True, width="stretch")
            else:
                ui.fail(res["pesan"])

# ---------------------------------------------------------------- Barang masuk
with tabs[1]:
    with st.form("f_masuk", clear_on_submit=True):
        st.markdown("#### Penerimaan barang dari pemasok")
        a, b = st.columns(2)
        pn = a.selectbox("Produk", nama_list, key="m_prod")
        qty = b.number_input("Jumlah diterima", min_value=0, step=1, value=0)
        c, d = st.columns(2)
        exp = c.date_input("Tanggal kedaluwarsa", value=md.TODAY + timedelta(days=180), min_value=md.TODAY)
        rak = d.selectbox("Letakkan di", ["Gudang Belakang", "Rak Tengah", "Rak Depan"])
        no = st.text_input("No. surat jalan", placeholder="SJ-2026-0001")
        ok_ = st.form_submit_button("Simpan Barang Masuk", type="primary")
    if ok_:
        p = by_name.loc[pn]
        err = []
        if qty <= 0: err.append("Jumlah diterima harus lebih dari 0.")
        if not no.strip(): err.append("No. surat jalan wajib diisi.")
        if exp <= md.TODAY: err.append("Tanggal kedaluwarsa harus setelah hari ini.")
        if (exp - md.TODAY).days > int(p.shelf_life) + 30: err.append(f"Tanggal kedaluwarsa melebihi masa simpan produk ({int(p.shelf_life)} hari). Periksa kembali.")
        if not ui.show_errors(err):
            res = stok_service.tambah_batch(int(p.produk_id), int(qty), exp, rak, user["nama"], jenis="masuk")
            ui.ok(res["pesan"])

# ---------------------------------------------------------------- Retur
with tabs[2]:
    jenis = st.radio("Jenis retur", ["Dari pelanggan", "Ke pemasok"], horizontal=True)
    with st.form("f_retur", clear_on_submit=True):
        a, b = st.columns(2)
        pn = a.selectbox("Produk", nama_list, key="r_prod")
        qty = b.number_input("Jumlah", min_value=0, step=1, value=0, key="r_qty")
        bl = batch[batch.nama == pn]
        bsel = st.selectbox("Batch", bl.batch_id.tolist(), format_func=lambda x: f"{x} · kedaluwarsa {bl.set_index('batch_id').loc[x, 'tgl_exp']:%d %b %Y} · stok {bl.set_index('batch_id').loc[x, 'qty']}") if len(bl) else None
        alasan = st.text_area("Alasan retur", placeholder="Kemasan penyok, salah kirim, mendekati kedaluwarsa, dll.")
        ok_ = st.form_submit_button("Simpan Retur", type="primary")
    if ok_:
        err = []
        if qty <= 0: err.append("Jumlah retur harus lebih dari 0.")
        if not bsel: err.append("Produk belum memiliki batch.")
        if len(alasan.strip()) < 5: err.append("Alasan retur wajib diisi (min. 5 karakter).")
        if not ui.show_errors(err):
            res = stok_service.retur(jenis, int(by_name.loc[pn].produk_id), int(qty), bsel, alasan, user["nama"])
            (ui.ok if res["ok"] else ui.fail)(res["pesan"])

# ---------------------------------------------------------------- Rusak
with tabs[3]:
    with st.form("f_rusak", clear_on_submit=True):
        a, b = st.columns(2)
        pn = a.selectbox("Produk", nama_list, key="x_prod")
        qty = b.number_input("Jumlah rusak", min_value=0, step=1, value=0, key="x_qty")
        bl = batch[batch.nama == pn]
        bsel = st.selectbox("Batch", bl.batch_id.tolist(), key="x_batch") if len(bl) else None
        penyebab = st.selectbox("Penyebab", ["Pecah / bocor", "Tersimpan salah suhu", "Rusak saat bongkar muat", "Dimakan hama", "Lainnya"])
        foto = st.file_uploader("Foto bukti (opsional)", type=["png", "jpg", "jpeg"])
        ok_ = st.form_submit_button("Simpan Barang Rusak", type="primary")
    if ok_:
        err = []
        if qty <= 0: err.append("Jumlah rusak harus lebih dari 0.")
        if not bsel: err.append("Produk belum memiliki batch.")
        if not ui.show_errors(err):
            res = stok_service.barang_rusak(int(by_name.loc[pn].produk_id), bsel, int(qty), penyebab, user["nama"])
            (ui.ok if res["ok"] else ui.fail)(res["pesan"])

# ---------------------------------------------------------------- Batch
with tabs[4]:
    with st.form("f_batch", clear_on_submit=True):
        st.markdown("#### Tambah batch (tanggal kedaluwarsa & jumlah)")
        a, b = st.columns(2)
        pn = a.selectbox("Produk", nama_list, key="b_prod")
        qty = b.number_input("Jumlah", min_value=0, step=1, value=0, key="b_qty")
        c, d = st.columns(2)
        exp = c.date_input("Tanggal kedaluwarsa", value=md.TODAY + timedelta(days=90), min_value=md.TODAY, key="b_exp")
        rak = d.selectbox("Rak", ["Rak Depan", "Rak Tengah", "Gudang Belakang"], key="b_rak")
        ok_ = st.form_submit_button("Simpan Batch", type="primary")
    if ok_:
        err = []
        if qty <= 0: err.append("Jumlah harus lebih dari 0.")
        if exp <= md.TODAY: err.append("Tanggal kedaluwarsa harus setelah hari ini.")
        if not ui.show_errors(err):
            res = stok_service.tambah_batch(int(by_name.loc[pn].produk_id), int(qty), exp, rak, user["nama"])
            ui.ok(res["pesan"])
    ui.section("Batch aktif", "Urut kedaluwarsa terdekat (FEFO).")
    q = st.text_input("Cari produk", key="cari_batch", placeholder="ketik nama produk…")
    tb = batch[batch.nama.str.contains(q, case=False)] if q else batch
    st.dataframe(tb[["batch_id", "nama", "qty", "tgl_exp", "sisa_hari", "rak"]].sort_values("tgl_exp").rename(
        columns={"batch_id": "Batch", "nama": "Produk", "qty": "Qty", "tgl_exp": "Kedaluwarsa", "sisa_hari": "Sisa hari", "rak": "Rak"}),
        hide_index=True, width="stretch", height=300)

ui.section("Riwayat mutasi terakhir")
mut = stok_service.get_mutasi()
if mut.empty:
    ui.empty_state("Belum ada mutasi pada sesi ini.")
else:
    st.dataframe(mut.rename(columns=str.title), hide_index=True, width="stretch")
