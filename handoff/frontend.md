# Frontend handoff (Agent 2)

Owner: Agent 2 (frontend). Branch: `feature/frontend` (do not merge to main).
Author: configured Git identity.

## Two frontends in the repo

| Path | Stack | Status |
| --- | --- | --- |
| `frontend/` | React 19 + Vite 8 + Tailwind v4 + `@figma/astraui` | **Primary.** Imported Figma Make design, wired to the backend contract. |
| `web/` | Vanilla HTML/CSS/JS | Earlier scaffold against the same contract; kept for reference. |

The `frontend/` app is the one that preserves the Figma Make visual design. If
the team wants a single frontend, `web/` can be retired.

## `frontend/` — import provenance

Imported the OUTER "Build STRIDE Guidance App" export only. The nested
`stride-frontend.zip` and macOS junk were excluded. Figma plugins in
`vite.config.ts` and the `.figma/` tooling are kept as-is (they work locally).

## Run it

Toolchain on the build machine: Homebrew Node 25, npm 11.6.2. No global
pnpm/mise/corepack, so use `npx pnpm@10.34.3` (the version pinned in `.mise.toml`).

```bash
cd frontend
npx pnpm@10.34.3 install            # 264 pkgs; Astra packages resolve on public npm
npx pnpm@10.34.3 run dev            # Vite dev server (PORT env, default 8443)
npx pnpm@10.34.3 run build          # production build -> dist/
npx pnpm@10.34.3 exec tsc --noEmit  # type check
```

Astra setup (per `node_modules/@figma/astraui-kit/guidelines/setup.md`) is
already satisfied by the export: `@figma/astraui/styles.css` imported in
`src/index.css`, `ThemeProvider` at the app root. No extra config needed.

Controller tests (no framework; Node native TS type-stripping):

```bash
node --experimental-strip-types tests/browser/controllers.test.ts   # 12/12
```

## Architecture (wiring)

```
src/App.tsx                 compose Landing + Dashboard inside ThemeProvider
src/components/Landing.tsx  landing page — appearance preserved exactly
src/components/Dashboard.tsx guidance/memory/settings — wired to real state
src/lib/useStride.ts        React hook composing all controllers
src/lib/api.ts              single adapter; fixture|real; /time+RTT clock; raw jpeg upload
src/lib/fixtures.ts         explicit Simulation mode (route + vision state machines)
src/lib/speech.ts           priority scheduler, dedupe by event_id, 1000ms live cutoff
src/lib/camera.ts           consent-gated capture loop, generation invalidation
src/lib/live.ts             no-overlap polling, backoff, abort on hide, stale suppression
src/lib/types.ts            contract DTOs
```

## Behavior delivered

- Landing appearance preserved (index.css byte-identical to import; hero/copy unchanged).
- Confirm / Repeat / Pause / Resume / Stop call `/route`; UI renders authoritative
  server route state, never increments locally. Repeat does not advance.
- User-gesture **Enable / test audio**. Status reports **browser speech readiness
  only** — no claim that AirPods are connected (the web app cannot select the iOS
  route).
- Consent gates **every** upload. Browser camera requires: Browser source + consent
  + explicit "Use this device's camera". Revoking consent stops uploads, bumps the
  capture generation, clears pending visual output.
- **Glasses (W11) mode never calls getUserMedia**; it consumes backend results.
- Live polling suppresses stale results (>1000 ms); speech dedupes by event_id;
  obstacle/fault priority cancels routine speech.
- Removed fabrications: invented distances ("8 metres") → position words; "AirPods
  connected" → browser-speech status; "Demo adapter" → real provider label (or
  "Simulation (fixtures)"); hardcoded sightings → `/memory`; device details → `/status`.
- Simulation is explicit and intentionally selected (mode selector), labeled
  wherever active. Never a silent fallback: real-mode errors surface in `state.lastError`.
- Settings are functional: text size sets `document.documentElement.dataset.textSize`;
  speech rate adjusts the scheduler; Light/Dark via Astra `useTheme`.

## Verified this session

- `pnpm install --frozen-lockfile`: 264 pkgs, exit 0.
- `tsc --noEmit`: exit 0 (Astra component prop types match the wiring).
- `pnpm run build`: exit 0 (25 modules, dist/ emitted).
- dev server: HTTP 200 on Vite 8.
- Controller tests: 12/12 pass.
- Headless Chrome boot of built app: Landing renders (hero title, Open STRIDE,
  brand-mark, Astra styling) with no app JS errors; appearance intact.

NOT verified (needs real devices/backend): live phone→hosted YOLO→phone,
actual AirPods playback, W11 transport, on-device mobile layout.

## Requests for Agent 1 (backend)

The `software` branch backend currently implements `/health`, `/time`
(`{server_ms}`) and a **multipart** `POST /frame`. The frontend consumes the full
contract: `/auth`, `/sessions`, `/sessions/{id}/camera`, `/routes`, `/route`,
`/status`, `/vision`, `/vision/latest`, `/perception`, `/memory`.

**Contract divergence:** `contracts/API.md` (and this frontend) use raw
`Content-Type: image/jpeg` + `X-*` headers for `/frame`; the current backend
parses `multipart/form-data`. Please reconcile to raw jpeg per the contract, or
propose a contract change. The adapter changes in one place (`src/lib/api.ts`).

README patch request: add a "Frontend (frontend/)" run section with the
`npx pnpm@10.34.3` commands above; backend serves the built `dist/` as
same-origin static files.
