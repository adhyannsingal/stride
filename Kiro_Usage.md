# Kiro Usage — STRIDE

An in-depth record of everything built with **Kiro** on the STRIDE project:
the backend (phases 1–3, `software` branch) and the frontend (`feature/frontend`
branch). It documents what was done, how, and the concrete verification evidence
captured while doing it.

STRIDE is an AI-powered navigation-assistance prototype for blind and low-vision
users: checked-route guidance with checkpoint confirmation, immediate obstacle
alerts, continuous "objects ahead" awareness, spoken feedback through the phone /
AirPods, and directional haptics. A wearable (W11 glasses camera + HC-SR04 sensor
+ ESP32 + motor) is the final integration target; development uses the browser
camera and simulated sensors, explicitly labeled.

> Honesty note carried throughout the build: this is a supervised prototype on a
> checked route with a sighted spotter. It is not validated for independent blind
> walking or road crossings. Missing detections never mean a clear path.

---

## 0. Repository map

```
stride/
├── Agent_1_Backend.md, Agent_2_Frontend.md, Agent_3_Hardware_Vision.md
├── Stride_Live_Vision_Requirements.md, contracts/API.md      # shared spec
├── frontend/            # Agent 2 — React/TS app (feature/frontend branch)
├── backend_phase1/ 2/ 3 # Agent 1 — FastAPI backend (software branch)
└── firmware/, app/vision/, tests/, qa/, handoff/
```

Branches:
- `main` — baseline planning docs (left untouched).
- `software` — backend phases 1–3 (teammate/Kiro backend work).
- `feature/frontend` — the frontend lane (Figma import + wiring + PWA).

---

## 1. Backend — built with Kiro (phases 1–3)

The backend is a Python **FastAPI** service, evolved across three milestones.
It is intentionally model-free at its core: the YOLO detector, firmware, UI and
physical haptics are supplied by teammates behind clean seams. It runs as **one
process / one Uvicorn worker / one replica** because live state and the frame
store live in memory.

### Phase 1 — Frame ingestion service
`backend_phase1/stride_backend/`

- **Endpoints:** `GET /health`, `GET /time` (`{"server_ms": <epoch ms>}`,
  no-store), `POST /frame` (multipart), Swagger at `/docs`.
- **Upload contract:** one `file` part (`image/jpeg`) plus text parts
  `session_id, device_id, boot_id, frame_id, sequence, captured_ms, source`
  (+ optional `origin`, `source_revision`). Identifiers trimmed, non-empty,
  ≤128 chars; sequence/time non-negative integers; `source ∈ {real, simulated,
  fixture}` ("availability is not a source").
- **Receipts:** 202 Accepted echoing identity/provenance + `receipt_id`,
  `received_ms`, `size_bytes`, `width`, `height`, `status=accepted`,
  `replaced_pending`, `freshness_basis=server_receipt`, `camera_clock_aligned=false`.
- **Validation / limits:** JPEG decoded off the event loop (bytes + orientation
  preserved). 512 KiB per JPEG, 4 MP decoded, 8 sessions, 16 device/boot
  sequence histories/session; whole multipart bounded to JPEG limit + 16 KiB;
  auth runs **before** body reads. Images never written to disk or logged.
- **Error envelope:** `{"error":{"code","message","fields":[]}}` — 422 bad
  metadata/JPEG, 401 token, 409 duplicate/regressing sequence or revision,
  413 oversize, 415 wrong media type, 400 malformed multipart, 429 capacity.
- **Security:** production startup **fails** if `STRIDE_DEVICE_TOKEN` is unset;
  the camera token must never ship in the phone frontend.
- **Modules:** `main.py` (app factory), `ingestion.py` (multipart guard),
  `store.py` (latest-frame store), `models.py`, `settings.py`, `errors.py`,
  `detector.py` (protocol).
- **Verified:** `pytest -q` → **58 passed**.

### Phase 2 — Session auth + continuous inference orchestration
`backend_phase2/stride_backend/`

- **Adds:** `POST /auth/session` (exchange a per-session secret for an
  HMAC-signed HttpOnly, SameSite=Strict, Secure-in-prod cookie, server-side
  expiry ~1h), `POST /vision` (idempotent session controls),
  `GET /vision/latest?session_id=...`, `GET /status?session_id=...`.
- **Continuous loop:** accepted frames are automatically dispatched to the
  detector while a session's vision is active — a single-latest-frame worker,
  one inference at a time, obsolete frames dropped (no backlog). Without a
  detector, controls still work and vision honestly reports `unavailable`,
  never `live`.
- **Dual auth model:** camera **device token** (uploads) is distinct from the
  **UI session** credential (results/controls). Browser uses the cookie
  (`credentials: "include"`); scripts may use `X-Session-Token`. CORS disabled
  by default; only exact configured `STRIDE_FRONTEND_ORIGINS` allowed. Unknown
  sessions denied; an authorized-but-not-started session returns `state=idle`,
  `status=unavailable`, empty objects.
- **New modules:** `auth.py`, `vision.py`, `worker.py` (over the Phase 1 base).
- **Verified:** `pytest -q` → **140 passed, 1 skipped** (the skip is the real
  YOLO adapter integration, which needs the model + a JPEG).

### Phase 3 — Checked-route navigation + SQLite route memory
`backend_phase3/stride_backend/`

- **Adds:** `GET /routes`, `POST /route` (canonical actions: start / confirm /
  repeat / pause / resume / stop with idempotent `action_id` + `expected_revision`),
  `GET /memory` (current/previous navigation progress, confirmed checkpoints,
  optional event history, last-seen sightings).
- **Persistence (SQLite, no ORM):** `STRIDE_DATABASE_PATH` (default
  `data/stride.sqlite3`); schema created at startup, non-destructive
  `CREATE IF NOT EXISTS`, schema-version guard (unknown future versions fail
  startup rather than being overwritten). Every op: own connection, foreign keys
  on, parameterized SQL, short `BEGIN IMMEDIATE` transactions, run in a thread
  pool. No images/secrets stored; DB files git-ignored.
- **Tables:** `routes`, `checkpoints`, `navigation_sessions`, `route_events`,
  `object_sightings`, `navigation_heads` (monotonic per-session revision),
  `route_actions` (idempotency, incl. rejected), `guidance_events`.
- **Safety-minded restart behavior:** previously *guiding* routes become
  *paused* and old cues are invalidated on restart; confirmed progress survives;
  a human must read `/memory`, verify, and explicitly resume. Blocked routes stay
  blocked — a restart or stale/unknown observation never clears an obstacle.
- **New modules:** `database.py`, `navigation.py`, `route_models.py`,
  `route_store.py`, `memory.py` (+ the `backend_phase3 2/` variant adds device
  integration: `device_api.py`, `device_auth.py`, `device_ingestion.py`,
  `devices.py`, `obstacles.py`, haptics).
- **Verified:** `pytest -q` → **184 passed, 1 skipped** (real-YOLO integration),
  matching the phase README.

### Backend verification summary (run locally this session)

| Phase | Command | Result |
| --- | --- | --- |
| 1 | `STRIDE_LOCAL_DEV=true pytest -q` | **58 passed** |
| 2 | `STRIDE_LOCAL_DEV=true pytest -q` | **140 passed, 1 skipped** |
| 3 | `STRIDE_LOCAL_DEV=true pytest -q` | **184 passed, 1 skipped** |

Python 3.13; deps pinned (FastAPI 0.135.2, Starlette, Pydantic 2, Uvicorn,
python-multipart, Pillow). The only skips are the real-detector integration
tests (model/hardware not present). One upstream Starlette/httpx deprecation
warning is expected.

---

## 2. Frontend — built with Kiro (`feature/frontend`)

The frontend owns `frontend/` (and an earlier vanilla `web/` scaffold). It
preserves the Figma Make visual design, is prepared for iPhone Home Screen use,
and is wired against the shared API contract. Teammates' backend/firmware were
never modified from this lane; nothing was merged to `main`.

### Toolchain
Vite 8 + React 19 + Tailwind v4 + the `@figma/astraui` design system. The build
machine has Homebrew Node 25 and npm, but no global pnpm/mise — so all commands
use `npx pnpm@10.34.3` (the version pinned in `.mise.toml`). The Astra packages
resolve from the public npm registry (no private registry needed).

### Commit history (chronological)

| Commit | What |
| --- | --- |
| `8bf03be` | Vanilla `web/` scaffold against the contract (adapter, camera loop, speech scheduler, route UI, fixtures, tests). |
| `0e03cc1` | Import the Figma Make React/TS export into `frontend/` (outer project only; nested `stride-frontend.zip` excluded). |
| `0f9500d` | Wire the React app to the contract: split components + controllers, route actions, consent gating, remove fabricated data. |
| `7b0ac2a` | Apply the updated Figma landing design (animated STRIDE stage, glasses image, scroll/swipe zoom transition). |
| `7b8e1ab` | Prepare iPhone Home Screen (PWA): manifest, STRIDE icons, Apple meta, safe-area spacing, a11y polish. |
| `9c78818` | Import the App-3 Figma export (phase-4 app with its own `src/app/` layer) while preserving the PWA presentation. |

### Current structure (`frontend/`)

```
frontend/
├── index.html                 # PWA/Apple meta + viewport-fit=cover (in Figma slots)
├── vite.config.ts             # Figma Make plugins (preserved)
├── .figma/make/site.json      # title "STRIDE" + svg favicon
├── public/
│   ├── manifest.webmanifest   # standalone, portrait, theme #145c50, maskable icons
│   ├── icon.svg / icon-maskable.svg
│   ├── icon-192.png / icon-512.png / icon-maskable-512.png
│   ├── apple-touch-icon.png   # 180×180, full-bleed
│   └── stride-glasses.png
└── src/
    ├── main.tsx               # React entry; imports index.css
    ├── App.tsx                # landing ↔ app switch, ThemeProvider
    ├── index.css              # global tokens + responsive + appended safe-area/a11y
    └── app/                   # App-3 export application layer
        ├── api.ts             # typed API client (auth/session, routes, vision, frame, memory)
        ├── controllers.ts     # SpeechController + BrowserCameraController
        ├── StrideApp.tsx      # main dashboard (guidance / memory / settings)
        └── app.css
```

### Behavior delivered (across the wiring + import commits)

- **Checked-route guidance:** Confirm / Repeat / Pause / Resume / Stop driven by
  the backend; the UI renders authoritative server state and never increments
  progress locally. Repeat never advances the checkpoint.
- **Consent-gated capture:** the browser camera only starts after explicit
  consent; revoking consent stops uploads and invalidates pending visual output.
  Glasses (W11) mode never calls `getUserMedia` — it consumes backend results.
- **Live awareness:** polls `/vision/latest`, suppresses stale results, dedupes
  speech events by ID, and lets obstacle/fault priority interrupt routine speech.
- **Honest status:** reports **browser speech readiness only** — it never claims
  AirPods are connected (the web app cannot select the iOS audio route). In the
  wired build, invented distances ("8 metres"), "AirPods connected", "Demo
  adapter" and hardcoded sightings were replaced with real backend state or an
  explicitly labeled **Simulation** mode. Simulation is intentionally selected,
  never a silent fallback after an error.
- **PWA / iPhone Home Screen:** installable as "STRIDE" with a green "S" icon,
  launches standalone, with safe-area insets for the notch / bottom tab bar /
  home indicator and ≥48px touch targets with visible focus.

> The App-3 export (`src/app/`) is the current canonical app and uses its own
> API shapes (`/auth/session`, `navigation_id` + `expected_revision`, multipart
> `/frame`, `VITE_STRIDE_API_URL` for the base URL). Live backend integration and
> functional debugging are handled separately.

### Frontend verification summary (run this session)

| Check | Result |
| --- | --- |
| `pnpm install --frozen-lockfile` | 264 pkgs, exit 0 |
| `tsc --noEmit` | exit 0 |
| `pnpm run build` | exit 0 (21 modules; JS 259.88 kB / 80.64 kB gzip, CSS 82.19 kB) |
| dev server (`pnpm run dev`) | HTTP 200 (Vite 8) |
| headless Chrome boot of `dist/` | landing renders, `#root` mounted, no app JS errors |
| built `index.html` | `<title>STRIDE>` + manifest + Apple meta present; icons emitted to `dist/` |

---

## 3. What is proven vs. still pending

**Proven locally:** backend phase test suites (58 / 140 / 184), frontend type
check + production build + dev boot + headless render, and PWA artifacts in the
build output.

**Still pending (needs a live backend / real hardware):**
- End-to-end phone → hosted detector → phone against a running backend exposing
  the full contract (the live wiring was validated against fixtures/types, not a
  running server).
- Real YOLO detection (the one skipped test per phase 2/3).
- Actual iPhone 14 + AirPods playback; on-device mobile layout.
- W11 glasses transport, HC-SR04 sensor, and physical haptics.

**Known integration note for whoever wires the backend to the App-3 frontend:**
match the export's exact API shapes (`/auth/session`, navigation revisions,
multipart `/frame`, `VITE_STRIDE_API_URL`). The `software`-branch backend already
implements `/health`, `/time`, `/frame`, `/auth/session`, `/vision*`, `/status`,
`/routes`, `/route`, `/memory` across phases 1–3; confirm field-level alignment
before the demo.

---

## 4. How to run everything

**Backend (any phase):**
```sh
cd backend_phase3
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements-dev.txt
STRIDE_LOCAL_DEV=true uvicorn stride_backend.main:create_app --factory \
  --host 127.0.0.1 --port 8000 --workers 1
python -m pytest -q          # 184 passed, 1 skipped
# Swagger: http://127.0.0.1:8000/docs
```

**Frontend:**
```sh
cd frontend
npx pnpm@10.34.3 install
npx pnpm@10.34.3 run dev      # Vite dev server (PORT env, default 8443)
npx pnpm@10.34.3 run build    # production build -> dist/
npx pnpm@10.34.3 exec tsc --noEmit
```

**iPhone Home Screen:** open the deployed HTTPS URL in Safari → Share → Add to
Home Screen. Installs as "STRIDE", launches standalone with safe-area spacing.
