# DemandWise - Database (Naila)

## Isi
- `backend/models.py` : 22 tabel (SQLAlchemy), jalan di PostgreSQL dan SQLite
- `backend/db.py`     : koneksi (`get_engine()`, `get_session()`)
- `scripts/muat_ke_postgres.py` : buat tabel + muat CSV data dummy Wulan
- `docs/erd.png`, `docs/erd.mermaid` : ERD

## Jalankan lokal (SQLite, tanpa Neon)
```
pip install -r requirements.txt
# taruh folder data_dummy/ (CSV dari Wulan) di folder proyek
python -m scripts.muat_ke_postgres --folder data_dummy
```
Hasilnya `demandwise.sqlite`. Login demo: `pemilik` / `demo123`.

## Jalankan di Neon
1. Buat project di Neon, salin connection string.
2. Isi `.streamlit/secrets.toml` (lihat `.example`), ATAU set variabel lingkungan `DEMANDWISE_DB_URL`.
3. `python -m scripts.muat_ke_postgres --folder data_dummy`

## Dipakai di kode backend
```python
from backend.db import get_session
from backend.models import BatchStok

with get_session() as s:
    batch = s.query(BatchStok).filter_by(produk_id=1, status="aktif").all()
```
Tanpa secrets dan tanpa variabel lingkungan, otomatis memakai SQLite lokal.

## Isi ulang / reset
- Data saja dikosongkan lalu diisi lagi: `python -m scripts.muat_ke_postgres --folder data_dummy --kosongkan`
- Skema berubah di `models.py`, tabel dibangun ulang: tambahkan `--reset`
- Untuk PostgreSQL skrip meminta konfirmasi `ya` (lewati dengan `--yes`).
