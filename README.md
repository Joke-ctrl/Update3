# THE MARKET KILL3R V2 — Backend

Production-oriented FastAPI backend for deterministic, explainable Smart Money Concepts market analysis. The backend preserves the original auth, MT5 ingest, signal and Railway contracts while adding a real multi-factor analysis pipeline.

## Current implementation

### Market data
- Validated, idempotent MT5 OHLC ingestion.
- Chronological bar validation before analysis.
- Correct latest-N bar loading (newest rows are selected, then restored to chronological order).
- Optional `X-MT5-API-Key` protection for MT5 bridge endpoints when `MT5_API_KEY` is configured.

### SMC engine
- Fractal swing highs/lows with strict inequalities.
- Explicit swing confirmation timing to prevent look-ahead.
- HH/HL/LH/LL labeling.
- Close-confirmed BOS and CHoCH with protected-swing sequencing.
- Displacement detection against preceding average range.
- Displacement-backed Fair Value Gaps with full-fill tracking.
- Displacement-backed Order Blocks with post-formation mitigation tracking.
- Equal-high/equal-low liquidity pools.
- Liquidity sweeps that only use pools already confirmed at the sweep time.
- Premium/discount dealing range and equilibrium.
- Asian/London/New York session context.
- SMT divergence with directionally correct inverse-correlation logic for pairs such as XAUUSD/DXY.
- Multi-timeframe evidence aggregation.

### Confluence and classification
The production pipeline is `app/engine/pipeline.py`.

It produces:
- `SETUP`
- `NO_SETUP`
- `INSUFFICIENT_CONFIRMATION`

A BUY/SELL direction is only emitted as a setup when:
1. Structure is confirmed.
2. At least three independent technical evidence categories agree.
3. Multi-timeframe context is not materially conflicting.
4. Confidence clears the configured threshold.
5. A high-impact event is not inside the configured blackout window.

News, economic events and fundamental context can confirm/reduce confidence but cannot create a setup on their own. The deterministic engine always owns the score, entry zone, invalidation, SL and TP levels.

### Explainability and persistence
Every persisted analysis run contains:
- Symbol and requested timeframes.
- Market bias.
- Direction and classification.
- Transparent weighted factor scores.
- Swing/structure evidence.
- FVGs.
- Order blocks.
- Liquidity sweeps and equal levels.
- Premium/discount/dealing range.
- Session context.
- SMT context.
- Economic-event context.
- News sentiment.
- Entry zone, invalidation, SL, TP1/TP2/TP3 and RR.
- Human-readable deterministic reasoning.

Dedicated evidence tables preserve the detector outputs for later dashboard/journal use.

### External context
- Economic calendar uses the existing JBlanked integration.
- CNBC RSS feeds remain the default news source.
- Anthropic is optional and narrative-only. It cannot change the deterministic classification, score or trade levels.
- DXY is automatically used as the default correlated instrument for USD-sensitive symbols when DXY bars are available.

## API

Existing endpoints remain versioned under `/api/v1`.

### Analysis
- `POST /api/v1/analysis/run` — run deterministic multi-timeframe analysis.
- `GET /api/v1/analysis/signals` — authenticated signal history.
- `GET /api/v1/analysis/runs/{run_id}` — authenticated full explainable analysis run.

### Market/MT5
- `POST /api/v1/mt5/ingest`
- `GET /api/v1/mt5/pending-signals`
- `POST /api/v1/mt5/execution-report`

Pending MT5 signals are now restricted to confirmed `SETUP` results; `NO_SETUP` and `INSUFFICIENT_CONFIRMATION` results are never exposed as executable signals.

### Context
- `GET /api/v1/calendar/upcoming`
- `GET /api/v1/news/latest`
- `GET /api/v1/health`

### Auth

Reconciled against the Flutter app's `BACKEND_API_CONTRACT.md` and its actual
`lib/services/auth_service.dart` / `api_service.dart` calls. All admin-gated
codes (registration approval, login OTP) are emailed only to `ADMIN_EMAIL`,
never to the user.

- `POST /api/v1/auth/register` — `{name, email, password}` → creates a
  pending (unapproved) account, emails a single-use registration code to
  the admin, returns `{"status": "pending_approval"}`. `409` on duplicate
  email.
- `POST /api/v1/auth/registration/verify` — `{email, code}` → approves the
  account. Does not return tokens.
- `POST /api/v1/auth/registration/resend` — `{email}` → revokes any
  outstanding code and issues/emails a new one.
- `POST /api/v1/auth/login` — `{email, password}` → `403
  {"status":"pending_approval"}` if not yet approved; otherwise, if
  `LOGIN_OTP_ENABLED`, emails an OTP to the admin and returns `{"status":
  "otp_required"}`; otherwise returns tokens directly.
- `POST /api/v1/auth/login/verify-otp` — `{email, code}` → returns
  `{access_token, refresh_token, token_type, user}`.
- `POST /api/v1/auth/refresh` — `{refresh_token}` → rotates the refresh
  token, returns a new `{access_token, refresh_token}`. `401` if
  expired/revoked/reused.
- `POST /api/v1/auth/logout` — bearer token required, body
  `{refresh_token}` → revokes that refresh token server-side. Always `2xx`.

Registration-approval codes and login OTPs are separate, single-use,
expiring, hashed-at-rest values (`registration_codes` / `login_otps`
tables) — a registration code can never be used as a login OTP or vice
versa, and neither can be reused once consumed.

## Database

Migration chain:
1. `1e08b51f5a74` — users
2. `9942621f6fdd` — market bars, signals and execution records
3. `3c1e5d9a7b42` — analysis runs, detector evidence, economic events/news and signal analysis metadata
4. `9112195c1d30` — `users.is_approved`, `registration_codes`, `login_otps`, `refresh_tokens` (admin-approval + OTP + refresh-token-rotation auth flow). Existing users with `is_active=true` are grandfathered as `is_approved=true` so pre-existing accounts are never locked out.

Run:

```bash
alembic upgrade head
```

## Environment

See `.env.example`.

Required in production:
- `SECRET_KEY`
- `DATABASE_URL`
- non-wildcard `CORS_ORIGINS`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` — required for
  registration-approval/OTP emails to actually deliver. Without these,
  registration and login still work, but codes are only logged
  server-side (see logs) rather than emailed — fine for local dev, not for
  production.

Optional:
- `MT5_API_KEY`
- `CALENDAR_API_KEY`
- `ANTHROPIC_API_KEY`
- `ADMIN_EMAIL` (defaults to `privateinv08@gmail.com`)
- `LOGIN_OTP_ENABLED` (defaults to `true`; set `false` to skip the login
  OTP step and issue tokens directly after password verification)
- `REGISTRATION_CODE_LENGTH`, `REGISTRATION_CODE_EXPIRE_MINUTES`,
  `LOGIN_OTP_LENGTH`, `LOGIN_OTP_EXPIRE_MINUTES`

## Railway

Existing Docker/Railway configuration is preserved:
- Dockerfile remains the deployment image.
- Railway starts with `python -m app.main`.
- Healthcheck remains `/api/v1/health`.
- Production/staging now reject the default JWT secret and wildcard CORS configuration.

## Render

`render.yaml` is a Render Blueprint using the same `Dockerfile` as Railway,
plus a managed Postgres database. It wires `DATABASE_URL` from the managed
DB automatically and marks `SMTP_*`/API-key variables `sync: false` so
you set their real values in the Render dashboard rather than committing
them. `CORS_ORIGINS` ships with a placeholder — set it to your real web
origin(s) if you have one; a native Flutter/mobile client never sends an
`Origin` header, so this setting doesn't affect it either way. Apply
migrations after the first deploy (Render shell or a release command):

```bash
alembic upgrade head
```

## Testing

Install development dependencies:

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Static validation:

```bash
python -m compileall app tests
```

The repository contains detector, structure, confluence, API and
regression tests, plus a full auth-flow suite in `tests/test_auth.py`
(register → admin-code approval → login → OTP → protected route →
refresh rotation → logout, and the corresponding rejection paths).

## Free market-data integrations

MarketKill3r now exposes authenticated market endpoints under `/api/v1/market`.

- **Live-Rates.com**: keyless development feed for live quotes (small free quota); supports major FX, XAU/USD and US30. Set `LIVE_RATES_API_KEY` if you have a key.
- **XAUS.com**: keyless XAU/USD spot fallback for the gold dashboard.
- **Twelve Data**: optional development/backfill adapter via `TWELVE_DATA_API_KEY`. Its free Basic plan is for internal/non-display use, so it is not used as the customer-facing chart feed.
- **JBlanked calendar** remains the primary economic-calendar provider via `CALENDAR_API_KEY`.
- **CNBC RSS** remains the default public news source; feeds are configurable with `NEWS_RSS_FEEDS`.
- **FMP** is reserved as an optional economic-calendar fallback via `FMP_API_KEY` and is not required for the free default setup.

For customer-facing chart candles, the existing MT5 ingestion endpoint remains the authoritative OHLC source. The new `/market/bars/{symbol}` endpoint reads only validated persisted bars; it never fabricates candles.
\n\n## MarketKill3r instrument support\n\nThe canonical symbols for the index instruments are `NAS100` (Nasdaq 100) and `US30` (Dow Jones 30). Common aliases such as `NASDAQ`, `NASDAQ100`, `US100`, `USTEC`, `DJ30`, `DOW30`, and `DOWJONES` are normalized before quote, bar, analysis, and MT5 ingestion lookups.\n\nThe dashboard instrument catalog is available at `GET /api/v1/market/instruments` for authenticated clients. Live pricing is provider-dependent; the MT5 bridge remains the authoritative path for validated OHLC bars used by the SMC analysis engine.\n