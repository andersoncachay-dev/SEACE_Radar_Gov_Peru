# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

"SEACE Radar" / "GovRadar" (product name **RODAR GovRadar CRM**) tracks government procurement processes in Peru (SEACE/OECE) and Chile (Mercado Público) for commercial teams, scoring/alerting on relevant opportunities and managing a post-discovery follow-up workflow ("Seguimiento de Oportunidades"). See `PRODUCT.md` for brand/UX intent. Backend is FastAPI + PostgreSQL; frontend is a hand-rolled React/TypeScript SPA; deployed to Azure Container Apps.

## Commands

### Backend (run from repo root — `backend/` is a package, tests/alembic assume root cwd)

```powershell
py -m pip install -r requirements.txt
py -m alembic upgrade head
py backend/scripts/seed_admin.py          # creates admin from ADMIN_EMAIL/ADMIN_PASSWORD (defaults: admin@seace-radar.local / Admin12345)
py -m uvicorn backend.app.main:app --reload
```

Or the wrapper: `.\run_backend.ps1` (does all of the above). Or Docker: `docker compose up --build` (Postgres on host port 5433, API on 8000, embedded scheduler `ENABLE_SCHEDULER=true`).

New migration: `py -m alembic revision --autogenerate -m "description"` — naming convention `YYYYMMDD_NNNN_description.py`. Several past migrations include data backfills, not just schema (e.g. `backend/alembic/versions/20260721_0026_backfill_proposal_stage_due_date.py`) — check for raw-SQL data steps before assuming a migration is schema-only.

Tests use plain `unittest` (no pytest fixtures, no `conftest.py`), with an in-memory SQLite engine per test file and router/service functions called directly (not via `TestClient`):

```powershell
python -m pytest backend/tests
python -m pytest backend/tests/test_alert_rules.py::AlertRuleManagementTests::test_some_case
```

### Frontend (`frontend/`)

```powershell
npm install
npm run dev        # Vite dev server, port 5173
npm run build       # tsc -b (typecheck) && vite build — this IS the typecheck step, there is no separate `typecheck` script
npm run preview
```

No lint or test tooling is configured (no ESLint, no vitest/jest) — don't assume `npm run lint`/`npm test` exist.

## Architecture

### Repo layout

- `backend/app/` — FastAPI app (current, productive system).
- `frontend/` — React/TS SPA (Vite), talks to backend only via `frontend/src/api.ts`.
- `azure/` — Container Apps Job YAML manifests, worker shell entrypoints, and `DEPLOYMENT.md` (deployment is entirely manual via Azure CLI — there is no `.github/workflows/` or any CI/CD).
- `src/` at repo root — **legacy Streamlit MVP**, predates `backend/`. Still has live dependents: some `backend/scripts/*.py` (e.g. `build_peru_publication_map.py`) import from `src/` (keyword matching, OECE/OCDS connectors), so don't treat it as dead code.

### Backend: layered structure

`backend/app/routers/*.py` are thin controllers (parse via `schemas.py`, delegate to services, return Pydantic models). `backend/app/services/*.py` own all DB queries/business logic against `backend/app/models.py`. `backend/app/main.py::create_app()` mounts ~15 routers, adds a `prevent_stale_api_responses` middleware forcing no-cache headers, and on `startup` calls `reconcile_interrupted_runs()` (closes any `ScrapeRun` left `queued`/`running` from a prior crash) then `start_scheduler()`.

Four standalone worker scripts at `backend/app/*.py` (not routers — direct service calls, used as Azure Container Apps Job entrypoints via `azure/run-*.sh`): `ingestion_worker.py`, `alert_worker.py`, `tracking_alerts_worker.py`, `tracking_date_refresh_worker.py`. Plus one-off/manual data scripts: `chile_region_backfill.py`/`_report.py`/`_manual_patch.py` (fix missing Chile `region` values) and `peru_publication_backfill.py`.

### Data model shape (`backend/app/models.py`)

`Opportunity` is the central entity (unique on `source`+`external_id`, soft-archive via `is_archived`/`archive_country`/`archive_key`), with 1:N `OpportunitySnapshot` (change history) and `Document`s. `SearchProfile` (manual or auto-generated) → `ScrapeRun` (1:N). `AlertRule` → `Alert`, deduped by unique `opportunity_id+rule_id+alert_type`, with `attempt_count`/`next_attempt_at` for retry.

Tracking subsystem ("Seguimiento"): `TrackingArea`/`TrackingResponsible` (M:N), `TrackingPhase` (per country) owns `TrackingStageTemplate`s (the reusable workflow definition, M:N to areas). `OpportunityTracking` (1:1 with `Opportunity`) instantiates `OpportunityTrackingStage` rows from templates per phase, each with M:N areas/assignees (assignee rows also track notification status). `OpportunityReview`/`OpportunityReviewComment` is a separate standby/review workflow, also 1:1 off `Opportunity`.

`User.access_profile` (`peru`/`chile`/`both`) plus `role` (`admin` or not) drives both UI page access and backend row-level filtering (see Auth below).

### Ingestion/scraping per country

`backend/app/radar_config.py::RADAR_COUNTRY_CONFIG` maps `peru` → source `oece_ocds_api` and `chile` → source `mercado_publico_lmp_gc`. Three distinct concepts not to conflate: **`RadarKeyword`** (a per-country keyword string, managed via `/radar-keywords`), **auto `SearchProfile`s** (one generated per country×keyword pair, named `"Radar automático · {label} · {keyword}"`, created/pruned by `scheduler_service.py::sync_radar_profiles`), and **manual `SearchProfile`s** (user-created, can point at other sources like `seace_public_browser`/Excel uploads via `services/seace_excel_service.py`).

`services/run_service.py::execute_scrape_run` branches by `source`: Chile computes a rolling "current month + next month" closing-date window (`chile_closing_window`) and optionally enriches detail pages; Peru reconciles against SEACE's published schedule (`_merge_seace_schedule`/`_peru_schedule_targets`). `services/ingestion_service.py::upsert_opportunities` does the actual dedupe/merge (content hash), and is careful to preserve archived/withdrawn rows and previously-collected amounts/schedule data against blank incremental re-scans.

### Dual-mode scheduler / "claim" pattern — the key non-obvious architecture piece

`backend/app/services/scheduler_service.py` supports two mutually-compatible ways to drive the same job functions (ingestion, tracking time-alerts, tracking date-refresh):

- **Embedded mode** (`ENABLE_SCHEDULER=true`, used in local/Docker): `start_scheduler()` runs an in-process APScheduler `BackgroundScheduler` with interval jobs.
- **External/claim mode** (`EXTERNAL_SCHEDULER_ENABLED=true`, used in Azure): there is no long-lived scheduler process. Instead each worker is invoked by an **Azure Container Apps Job cron trigger**, and on every invocation calls a `claim_*_run()` function that atomically checks a `next_update_at` due-time persisted in `AppSetting` (e.g. `scheduler.{country}.next_update_at`). If `now < due_at` it's a no-op exit; if due, it advances `due_at` by the configured interval and does the real work.

This means **the Container Apps Job's cron frequency and the actual work interval are two separate knobs** — the interval is admin-editable at runtime (`Sistema > Verificación automática` in the UI, backed by `AppSetting` rows / `TRACKING_ALERT_INTERVAL_MINUTES` / `TRACKING_DATE_REFRESH_INTERVAL_MINUTES` env defaults), while the cron in `azure/*-job.yaml` is static and only needs to fire *at least* as often as the shortest interval an admin might configure — firing more often than that just wastes container-start compute with no functional benefit. (As of 2026-07-30 the cron values were tightened to match each job's default interval — ingestion peru/chile every 15 min offset, tracking-alerts every 30 min, date-refresh every 3h — after this mismatch was found to be the dominant Azure Container Apps cost driver. A true dynamic sync, where changing the interval in the UI also rewrites the job's cron via the Azure Resource Manager API, was considered but not implemented — out of scope, would need the backend's managed identity granted Container Apps Job Contributor.)

### Tracking module ("Seguimiento de Oportunidades")

Post-discovery workflow: assign an opportunity to `TrackingArea`s/`TrackingResponsible`s, walk it through country-specific `TrackingPhase`s built from reusable `TrackingStageTemplate`s (with computed due dates, e.g. `compute_cotizacion_due_dates`), and record a `quotation_outcome`. `services/tracking_service.py` implements `start_tracking`, `advance_phase`, `toggle_stage`, area/assignee updates, and `evaluate_time_status_alerts` (computes per-stage "atender"/"urgente" status against `due_date`, fires each alert level once via flags on the stage). `services/tracking_date_refresh_service.py` re-scrapes source dates for actively-tracked opportunities and diffs against stored deadlines, emitting change alerts. `services/tracking_notification_service.py` sends the actual emails for all of the above. Routers: `tracking_areas.py`, `tracking_responsibles.py`, `tracking_templates.py` (org/workflow catalog CRUD), `opportunity_tracking.py` (main workflow endpoints + xlsx export), `opportunity_reviews.py` (separate standby/review+comments flow), `opportunity_view_states.py` (per-user saved UI filters, adjacent but unrelated to the tracking workflow).

### Alerts/notifications

`services/notification_service.py::evaluate_alerts` matches active `Opportunity` rows against `AlertRule`s (keyword, `min_priority`, country, `hours_before_deadline`) creating deduped `Alert` rows. `send_pending_alerts` dispatches by channel: **email** via Azure Communication Services (`EMAIL_PROVIDER=azure`) or SMTP (default); **whatsapp** via Azure ACS WhatsApp templates or a generic webhook (`WHATSAPP_API_URL`/`WHATSAPP_TOKEN`). Retries use `attempt_count`/`next_attempt_at` capped by `ALERT_MAX_ATTEMPTS`/`ALERT_RETRY_BASE_MINUTES`. Note `alert_worker.py` (procurement/keyword alerts) has no claim/interval logic — it runs unconditionally every invocation, unlike `tracking_alerts_worker.py` (tracking deadline alerts), which does use the claim pattern.

### Auth

Custom HMAC-SHA256 signed token in `backend/app/security.py` (`create_access_token`/`parse_access_token`) — **not** a standard JWT library, despite using the OAuth2-password-flow shape (`OAuth2PasswordBearer`/`OAuth2PasswordRequestForm`). Passwords are PBKDF2-hashed. `dependencies.py::get_current_user`/`require_admin` gate endpoints; `source_is_allowed`/`require_source_access` filter which `source` rows (Peru vs Chile) a user can see based on `User.access_profile`, independent of role.

### Frontend

Deliberately minimal dependency footprint — no router, no global state library, no UI kit, no HTTP client library (`frontend/package.json` has essentially just React + Vite + TS). Consequences to keep in mind when extending it:

- **Routing** is a hand-rolled `Page` union type + `useState` switch in `frontend/src/main.tsx` (not React Router) — there is no URL/history sync, refreshing always returns to the default page. Country-specific screens (Home, Opportunities, Archived, Tracking) are separate `Page` entries rather than one page parameterized by country at the routing layer.
- **All API calls** go through the single module `frontend/src/api.ts` — this file is effectively a map of the entire backend surface consumed by the UI. Auth token lives in `localStorage` (`rodar_token`), attached per-call, no global 401 interceptor.
- **Server state**: no React Query — `useBackend(token)` hook in `main.tsx` fetches everything in parallel and polls every 60s while the tab is visible, passed down via props (prop drilling, no Context).
- **Styling**: one global stylesheet `frontend/src/styles.css` (~9,900 lines) with CSS custom properties for the brand palette; no component library or separate theme file.
- Access to pages is gated client-side by `profilePages` keyed on `access_profile`/`role` — mirrors (but does not replace) the backend's own `source`-based row filtering.

### Deployment (Azure)

Resource group `govradar-rg` (Central US): Container Apps `govradar-api` + `govradar-frontend`, Container Apps Jobs for ingestion (peru/chile), alert-worker, tracking-alerts, tracking-date-refresh (peru/chile), a migration job (`govradar-migrate`, runs `alembic upgrade head`, started manually via CLI — no YAML committed for it), Postgres Flexible Server `govradar-db-rodar`, Key Vault `govradarkv923fd1`, and managed identity `govradar-identity`. All jobs share one Docker image (`Dockerfile` at repo root — installs Chromium for Selenium scrapers) with different `command:` entrypoints per `azure/run-*.sh`.

**Notable quirk**: due to a subscription quota limit, GovRadar reuses an unrelated project's Container Apps Environment and ACR (`pgi-hughesnet-rg` / `pgihughesnetacr.azurecr.io`, see `azure/provision-base.ps1`) instead of provisioning its own — apps/data stay logically isolated by `govradar-*` naming, but don't assume the environment or registry are dedicated to this project when investigating infra. ACR Tasks is also blocked on this subscription, so images are built locally with Docker and pushed manually. See `azure/DEPLOYMENT.md` for the full manual deploy sequence.
