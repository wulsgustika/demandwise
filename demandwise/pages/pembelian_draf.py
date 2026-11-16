"""Staf Pembelian: daftar rekomendasi pembelian & form draf pesanan."""
import streamlit as st

from backend import pembelian_service
from components import ui

ui.require_role("Staf Pembelian", "Manajer")
user = ui.current_user()
ui.page_header("Rekomendasi Pembelian & Draf Pesanan", "Jumlah beli = prediksi lead time + safety stock − stok − pesanan berjalan, dibatasi masa simpan.")

df = pembelian_service.get_rekomendasi_pembelian()
c1, c2, c3 = st.columns([1.2, 1.2, 1])
kat = c1.selectbox("Kategori", ["Semua"] + sorted(df.kategori.unique()))
pem = c2.selectbox("Pemasok", ["Semua"] + sorted(df.pemasok.unique()))
hanya = c3.toggle("Hanya yang perlu dibeli", value=True)
v = df.copy()
if kat != "Semua": v = v[v.kategori == kat]
if pem != "Semua": v = v[v.pemasok == pem]
if hanya: v = v[v.rekomendasi > 0]

ui.kpi_row([
    dict(label="Produk perlu dibeli", value=str((df.rekomendasi > 0).sum()), tone="orange"),
    dict(label="Dibatasi masa simpan", value=str((df.catatan == "Dibatasi masa simpan").sum()), tone="blue"),
    dict(label="Ditunda (risiko exp)", value=str(df.catatan.str.startswith("Ditunda").sum()), tone="red"),
    dict(label="Estimasi nilai", value=ui.rp_short((df.disarankan * df.hpp).sum()), tone="green"),
])
ui.section("Pilih item untuk draf", "Centang item dan sesuaikan jumlah pesan. Jumlah tidak boleh melebihi batas masa simpan.")
ed = v[["produk_id", "nama", "pemasok", "stok", "pred_lt", "safety", "berjalan", "rekomendasi", "maks_umur_simpan", "disarankan", "catatan"]].copy()
ed.insert(0, "Pilih", False)
ed["Qty Pesan"] = ed.disarankan
res = st.data_editor(
    ed, hide_index=True, width="stretch", height=380, key=f"po_ed_{kat}_{pem}_{hanya}",
    disabled=[c for c in ed.columns if c not in ("Pilih", "Qty Pesan")],
    column_config={"produk_id": None, "nama": st.column_config.TextColumn("Produk", width="medium"), "pemasok": "Pemasok", "stok": "Stok", "pred_lt": st.column_config.NumberColumn("Prediksi LT"),
                   "safety": "Safety", "berjalan": "Berjalan", "rekomendasi": "Rekomendasi", "maks_umur_simpan": st.column_config.NumberColumn("Maks (masa simpan)"),
                   "disarankan": "Disarankan", "catatan": "Catatan",
                   "Qty Pesan": st.column_config.NumberColumn("Qty Pesan", min_value=0, step=1)},
)
pilih = res[res.Pilih].merge(v[["produk_id", "hpp"]], on="produk_id")
if len(pilih):
    pilih["Nilai"] = pilih["Qty Pesan"] * pilih.hpp
    st.markdown(f"**{len(pilih)} item dipilih** · total estimasi **{ui.rp(pilih.Nilai.sum())}** · {pilih.pemasok.nunique()} pemasok → {pilih.pemasok.nunique()} draf PO")
if st.button("Buat Draf Pesanan", type="primary", disabled=len(pilih) == 0):
    err = []
    if (pilih["Qty Pesan"] <= 0).any():
        err.append("Qty pesan harus lebih dari 0 untuk semua item terpilih.")
    for _, o in pilih[pilih["Qty Pesan"] > pilih.maks_umur_simpan].iterrows():
        err.append(f"{o.nama}: qty melebihi batas masa simpan ({int(o.maks_umur_simpan)}).")
    for _, o in pilih[pilih.catatan.str.startswith("Ditunda")].iterrows():
        err.append(f"{o.nama}: pemesanan ditunda karena ada batch berisiko kedaluwarsa.")
    if not ui.show_errors(err):
        items = [dict(produk_id=int(o.produk_id), nama=o.nama, pemasok=o.pemasok, qty=int(o["Qty Pesan"]), hpp=float(o.hpp)) for _, o in pilih.iterrows()]
        out = pembelian_service.buat_draf(items, user["nama"])
        ui.ok(out["pesan"])
        st.info("Buka menu **Alur & Status Pesanan** untuk mengajukan draf ke Manajer.")
