# MarketKill3r backend

This folder is the FastAPI/SQLAlchemy backend. It is intentionally separate from
the Flutter application.

## Core pieces

- `app/api/routes/` — auth, users, market, analysis, calendar, news and MT5 APIs.
- `app/engine/` — deterministic SMC detectors and confluence pipeline.
- `app/services/` — market data, calendar, news, persistence and instrument catalog.
- `app/models/` and `app/schemas/` — database/API contracts.
- `migrations/` — Alembic migrations.
- `tests/` — backend test suite.

## Index support

`NAS100` and `US30` are canonical symbols. Common aliases are normalized before
market, analysis and MT5 bar operations.

Important: the backend does not invent market prices. The MT5 bridge can ingest
validated OHLC bars, and analysis correctly returns insufficient-data status when
bars have not been supplied.

Run the backend from this folder after configuring `.env`:

```powershell
python -m uvicorn app.main:app --reload
```
