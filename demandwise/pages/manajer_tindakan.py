"""Manajer: persetujuan / penolakan tindakan untuk batch berisiko kedaluwarsa."""
import pandas as pd
import streamlit as st

from backend import stok_service
from backend.ml import expiry
from components import ui

ui.require_role("Manajer")
user = ui.current_user()
ui.page_header("Tindakan Batch Berisiko", "Setujui rekomendasi sistem, tolak, atau tetapkan tindakan lain. Keputusan otomatis menjadi tugas Gudang.")

r = expiry.get_risiko_kedaluwarsa()
risk = r[r.berisiko > 0]
antre = risk[risk.keputusan == "Menunggu"].sort_values(["sisa_hari", "nilai_risiko"], ascending=[True, False])
ui.kpi_row([
    dict(label="Menunggu keputusan", value=str(len(antre)), tone="orange"),
    dict(label="Kritis", value=str((antre.level == "Kritis").sum()), tone="red"),
    dict(label="Nilai berisiko", value=ui.rp_short(antre.nilai_risiko.sum()), tone="red"),
    dict(label="Sudah diputuskan", value=str((risk.keputusan != "Menunggu").sum()), tone="green"),
])
tab1, tab2 = st.tabs([f"Menunggu keputusan ({len(antre)})", "Riwayat keputusan"])
with tab1:
    lv = st.segmented_control("Level", ["Semua", "Kritis", "Siaga", "Waspada"], default="Semua")
    v = antre if lv in (None, "Semua") else antre[antre.level == lv]
    if v.empty: ui.empty_state("Tidak ada batch yang menunggu keputusan.")
    for x in v.itertuples():
        with st.expander(f"{x.level.upper()} · {x.nama} · batch {x.batch_id} · berisiko {x.berisiko} unit · sisa {x.sisa_hari} hari", expanded=False):
            rek = expiry.get_rekomendasi_tindakan(x.batch_id)
            a, b = st.columns([1.1, 1])
            with a:
                st.markdown(f"{ui.badge(x.level)} &nbsp; Kedaluwarsa **{x.tgl_exp:%d %b %Y}** · Stok batch **{x.qty}** · Proyeksi laku **{x.proyeksi_laku}** · Berisiko **{x.berisiko}** (≈ {ui.rp(x.nilai_risiko)})", unsafe_allow_html=True)
                st.markdown(f"**Rekomendasi sistem:** {rek['tindakan_utama']}")
                d = pd.DataFrame(rek["diskon_bertahap"]).rename(columns={"tahap": "Tahap", "diskon": "Diskon %", "harga": "Harga", "margin": "Margin %"})
                st.dataframe(d, hide_index=True, width="stretch", column_config={"Harga": st.column_config.NumberColumn(format="Rp %d")})
                st.caption(f"Harga tidak boleh di bawah HPP ({ui.rp(rek['harga_min'])}). Bundling: **{rek['bundling']}** · Retur pemasok: {'layak' if rek['retur_layak'] else 'tidak layak'}")
            with b:
                with st.form(f"fm_{x.batch_id}"):
                    kep = st.radio("Keputusan", ["Setujui rekomendasi", "Tolak", "Tetapkan tindakan lain"], key=f"k_{x.batch_id}")
                    lain = st.selectbox("Tindakan lain", ["Diskon khusus", "Bundling", "Retur ke pemasok", "Donasi", "Pindah rak promosi"], key=f"l_{x.batch_id}")
                    cat = st.text_area("Catatan", key=f"c_{x.batch_id}", placeholder="Wajib bila menolak / tindakan lain")
                    go = st.form_submit_button("Simpan Keputusan", type="primary", width="stretch")
                if go:
                    err = []
                    if kep != "Setujui rekomendasi" and len(cat.strip()) < 5: err.append("Catatan wajib diisi (min. 5 karakter) untuk keputusan ini.")
                    if not ui.show_errors(err):
                        kode = {"Setujui rekomendasi": "Setujui", "Tolak": "Tolak", "Tetapkan tindakan lain": "Lainnya"}[kep]
                        tind = rek["tindakan_utama"] if kode == "Setujui" else (lain if kode == "Lainnya" else "-")
                        res = expiry.proses_tindakan(x.batch_id, kode, tind, cat, user["nama"])
                        ui.ok(res["pesan"])
                        st.rerun()
with tab2:
    from backend.state import store
    h = pd.DataFrame([dict(batch=k, **v) for k, v in store()["tindakan"].items()])
    if h.empty: ui.empty_state("Belum ada keputusan.")
    else:
        st.dataframe(ui.color_cells(h[["batch", "nama", "keputusan", "tindakan", "catatan", "oleh", "waktu"]].rename(columns=str.title), ["Keputusan"]), hide_index=True, width="stretch")
