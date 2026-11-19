from backend.pembelian import hitung_qty_beli


def test_beli_normal_di_bawah_batas():
    # butuh 30+10-20-5 = 15; batas 4*10 = 40 -> 15
    r = hitung_qty_beli(stok=20, prediksi_lead_time=30, safety_stock=10,
                        pesanan_berjalan=5, prediksi_harian=4, sisa_umur_simpan=10)
    assert r == {"qty_hitung": 15, "batas_masa_simpan": 40, "qty_rekomendasi": 15}


def test_dibatasi_masa_simpan():
    # butuh 100, tapi batas 5*6 = 30 -> 30
    r = hitung_qty_beli(stok=0, prediksi_lead_time=90, safety_stock=10,
                        pesanan_berjalan=0, prediksi_harian=5, sisa_umur_simpan=6)
    assert r["qty_hitung"] == 100
    assert r["qty_rekomendasi"] == 30


def test_stok_cukup_hasil_nol():
    r = hitung_qty_beli(stok=100, prediksi_lead_time=20, safety_stock=5,
                        pesanan_berjalan=0, prediksi_harian=2, sisa_umur_simpan=30)
    assert r["qty_hitung"] == 0
    assert r["qty_rekomendasi"] == 0


def test_pesanan_berjalan_dikurangi():
    r = hitung_qty_beli(stok=0, prediksi_lead_time=20, safety_stock=5,
                        pesanan_berjalan=25, prediksi_harian=5, sisa_umur_simpan=30)
    assert r["qty_rekomendasi"] == 0


def test_pembulatan_ke_atas():
    r = hitung_qty_beli(stok=0, prediksi_lead_time=10.2, safety_stock=0,
                        pesanan_berjalan=0, prediksi_harian=5, sisa_umur_simpan=30)
    assert r["qty_rekomendasi"] == 11


def test_umur_simpan_tidak_diketahui_tanpa_batas():
    r = hitung_qty_beli(stok=0, prediksi_lead_time=20, safety_stock=4,
                        pesanan_berjalan=0, prediksi_harian=1, sisa_umur_simpan=None)
    assert r == {"qty_hitung": 24, "batas_masa_simpan": None, "qty_rekomendasi": 24}
