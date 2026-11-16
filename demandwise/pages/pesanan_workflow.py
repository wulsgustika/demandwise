"""Alur pesanan: Staf Pembelian -> Manajer (review) -> Pemilik (setuju/revisi) -> pemasok -> jadwal kirim."""
import pandas as pd
import streamlit as st

from backend import mock_data as md
from backend import pembelian_service as ps
from components import ui

ui.require_role("Staf Pembelian", "Manajer", "Pemilik")
user = ui.current_user()
role = user["role"]
ui.page_header("Alur & Status Pesanan", "Draf → Review Manajer → Persetujuan Pemilik → Kirim ke pemasok → Konfirmasi jadwal kirim.")

po_all = ps.get_pesanan()
perlu = {"Staf Pembelian": ("Draf", "Revisi", "Disetujui", "Dikirim ke Pemasok"), "Manajer": ("Review Manajer",), "Pemilik": ("Persetujuan Pemilik",)}[role]
ui.kpi_row([
    dict(label="Total pesanan", value=str(len(po_all)), tone="navy"),
    dict(label="Perlu tindakan Anda", value=str(sum(p["status"] in perlu for p in po_all)), tone="orange"),
    dict(label="Disetujui / berjalan", value=str(sum(p["status"] in ("Disetujui", "Dikirim ke Pemasok") for p in po_all)), tone="blue"),
    dict(label="Jadwal terkonfirmasi", value=str(sum(p["status"] == "Jadwal Terkonfirmasi" for p in po_all)), tone="green"),
])
f = st.segmented_control("Tampilkan", ["Perlu tindakan saya", "Semua", "Selesai"], default="Perlu tindakan saya")
sel = [p for p in po_all if (f == "Semua") or (f == "Selesai" and p["status"] == "Jadwal Terkonfirmasi") or (f in (None, "Perlu tindakan saya") and p["status"] in perlu)]
if not sel:
    ui.empty_state("Tidak ada pesanan pada filter ini.")

for po in sel:
    nilai = ps.nilai_po(po)
    with st.expander(f"{po['id']} · {po['pemasok']} · {ui.rp(nilai)} · {po['status']}", expanded=po["status"] in perlu):
        st.markdown(ui.badge(po["status"]), unsafe_allow_html=True)
        ui.stepper(ps.ALUR if po["status"] != "Revisi" else ["Revisi"] + ps.ALUR[1:], po["status"] if po["status"] != "Revisi" else "Revisi")
        if po["jadwal"]:
            st.success(f"Jadwal kirim terkonfirmasi: **{po['jadwal']:%A, %d %B %Y}**")
        a, b = st.columns([1.3, 1], gap="large")
        with a:
            df = pd.DataFrame(po["items"])
            df["Subtotal"] = df.qty * df.hpp
            editable = role == "Staf Pembelian" and po["status"] in ("Draf", "Revisi")
            out = st.data_editor(df[["nama", "qty", "hpp", "Subtotal"]].rename(columns={"nama": "Produk", "qty": "Qty", "hpp": "HPP"}), hide_index=True, width="stretch",
                                 key=f"it_{po['id']}_{po['status']}", disabled=not editable if not editable else ["Produk", "HPP", "Subtotal"],
                                 column_config={"HPP": st.column_config.NumberColumn(format="Rp %d"), "Subtotal": st.column_config.NumberColumn(format="Rp %d"),
                                                "Qty": st.column_config.NumberColumn(min_value=1, step=1)})
            if editable and st.button("Simpan perubahan qty", key=f"sv_{po['id']}"):
                if (out.Qty <= 0).any(): ui.show_errors(["Qty harus lebih dari 0."])
                else:
                    r = ps.ubah_item(po["id"], [dict(produk_id=int(i["produk_id"]), nama=i["nama"], qty=int(q), hpp=i["hpp"]) for i, q in zip(po["items"], out.Qty)])
                    ui.ok(r["pesan"]); st.rerun()
        with b:
            st.markdown("**Riwayat**")
            for w, o, t in reversed(po["log"]):
                st.markdown(f"<div class='s' style='font-size:.85rem'><b>{t}</b><br><span style='color:#475569'>{o} · {w}</span></div>", unsafe_allow_html=True)
        st.divider()
        cat = st.text_input("Catatan (wajib untuk revisi / pengembalian)", key=f"ct_{po['id']}")

        def do(aksi, jadwal=None, wajib_catatan=False):
            if wajib_catatan and len(cat.strip()) < 5:
                ui.show_errors(["Catatan minimal 5 karakter diperlukan untuk aksi ini."]); return
            r = ps.pesanan_aksi(po["id"], aksi, user, cat, jadwal)
            (ui.ok if r["ok"] else ui.fail)(r["pesan"])
            if r["ok"]: st.rerun()

        s = po["status"]
        c = st.columns(3)
        if role == "Staf Pembelian":
            if s in ("Draf", "Revisi") and c[0].button("Ajukan ke Manajer", key=f"aj_{po['id']}", type="primary", width="stretch"): do("ajukan")
            if s == "Disetujui" and c[0].button("Kirim ke Pemasok", key=f"kr_{po['id']}", type="primary", width="stretch"): do("kirim")
            if s == "Dikirim ke Pemasok":
                jd = c[0].date_input("Jadwal kirim dari pemasok", value=md.TODAY + pd.Timedelta(days=3), min_value=md.TODAY, key=f"jd_{po['id']}")
                if c[1].button("Simpan Konfirmasi Jadwal", key=f"kj_{po['id']}", type="primary", width="stretch"): do("konfirmasi_jadwal", jd)
        if role == "Manajer" and s == "Review Manajer":
            if c[0].button("Teruskan ke Pemilik", key=f"tf_{po['id']}", type="primary", width="stretch"): do("teruskan")
            if c[1].button("Kembalikan (revisi)", key=f"kb_{po['id']}", width="stretch"): do("kembalikan", wajib_catatan=True)
        if role == "Pemilik" and s == "Persetujuan Pemilik":
            if c[0].button("Setujui Pesanan", key=f"st_{po['id']}", type="primary", width="stretch"): do("setujui")
            if c[1].button("Minta Revisi", key=f"rv_{po['id']}", width="stretch"): do("revisi", wajib_catatan=True)
        if s not in perlu:
            st.caption("Tidak ada aksi untuk Anda pada status ini.")
