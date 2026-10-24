# Kiro usage and evidence — STRIDE

STRIDE is a Hackachusetts 2026 assistive navigation prototype for blind and low-vision users. This page consolidates the team's existing Kiro account with the current merged repository. It separates reported Kiro work from what source history and tests independently establish. The current application combines a React/TypeScript phone web app, FastAPI, an ONNX YOLO detector, checked-route navigation, SQLite memory, and ESP32 camera/controller work. It is a supervised prototype, not a validated mobility aid.

## Kiro's reported role

The earlier [Kiro usage account](https://github.com/adhyannsingal/stride/blob/3e71e21990d2341d937f09192085fbc2144fb786/Kiro_Usage.md), committed on the frontend branch as [3e71e21](https://github.com/adhyannsingal/stride/commit/3e71e21990d2341d937f09192085fbc2144fb786), reports Kiro-assisted backend Phases 1–3 and frontend development. It records workflow choices, milestones, commands and historical test results. This is a team-authored report. The repository does not contain Kiro chat transcripts or session metadata that independently attribute each code change to a particular Kiro run. Treat that attribution as **reported, not independently verified**; commit history verifies code changes, not the tool that produced them.

The original report predates [PR #2](https://github.com/adhyannsingal/stride/pull/2). Its statements that main had only planning files, that the frontend had not merged, and that Phase 4 lived in a separate variant are obsolete. The combined application now lives on main, with the active backend under [backend_phase3/](backend_phase3/) and the web app under [frontend/](frontend/).

## Documented milestones and workflows

| Milestone in original Kiro account | Repository outcome | Attribution limit |
| --- | --- | --- |
| Backend Phase 1 | Authenticated multipart JPEG ingestion, bounded latest-frame store and detector protocol; see [Phase 1 README](backend_phase1/README.md). Historical report: 58 passing tests. | Kiro involvement reported by the original account; no session record in Git. |
| Backend Phase 2 | Session authentication, continuous inference worker and live vision APIs; see [Phase 2 README](backend_phase2/README.md). Historical report: 140 passed, 1 skipped. | Same attribution limit. |
| Backend Phase 3 | Checked-route controller, SQLite persistence and last-seen memory; see [current backend README](backend_phase3/README.md). Historical report: 184 passed, 1 skipped. | Same attribution limit. |
| Frontend | Figma import, contract wiring, landing design and iPhone Home Screen preparation. Source milestones include [8bf03be](https://github.com/adhyannsingal/stride/commit/8bf03be1f47510ba2e3033bd590f3a864c703383), [0f9500d](https://github.com/adhyannsingal/stride/commit/0f9500d578f4de147ed056d102512127991c077b), and [7b8e1ab](https://github.com/adhyannsingal/stride/commit/7b8e1abeda328e8e99db0f29e1872f10954f6dbc). | Kiro involvement reported; commits establish changes only. |

The original account describes an iterative workflow: define endpoint contracts, implement a bounded component, run local tests, review the result, then wire UI controls to server state. It distinguishes fixture data from physical inputs and keeps route progression tied to explicit confirmation. Those are documented design choices; the report is not a prompt log or native Kiro execution trace.

A separate committed [.kiro reference set](https://github.com/adhyannsingal/stride/commit/45e8c095b8679b2feb4529d4bd17f60e4380af93) contained steering and retrospective backend requirements/design/tasks. Its own README says it was prepared from existing implementation for **future** Kiro sessions, not used as a native spec before the work. It was subsequently [removed](https://github.com/adhyannsingal/stride/commit/3ef99e9bd3438b0b7c0aa0771edda549322c6604). We reference that original history rather than restoring dated specifications as if they guided completed code. The new steering files in this PR describe the current project for future Kiro work. No hooks, MCP integrations, custom agents, Crew, or Powers usage is asserted.

## Current architecture and other contributions

[PR #2](https://github.com/adhyannsingal/stride/pull/2) merged frontend and Phase 4 backend integration. The active FastAPI app under [backend_phase3/stride_backend/](backend_phase3/stride_backend/) retains the Phase 1–3 APIs and adds controller pairing, authenticated telemetry, conservative obstacle classification, navigation holds, expiring haptic commands and acknowledgments. See the [device contract](backend_phase3/DEVICE_INTEGRATION.md). The React app under [frontend/src/app/](frontend/src/app/) supports route controls, browser-camera fallback, live-result polling and browser speech. [app/vision/](app/vision/) provides the real ONNX YOLO adapter and tracking. [firmware/](firmware/) contains ESP32 camera and feedback code.

These later capabilities are visible in source and tests, but the original Kiro usage account does **not** establish that Kiro built Phase 4, the model, firmware, later frontend/backend integration, or browser-camera fallback. Their tool attribution remains unverified. The model is real code; its presence does not prove that the full hosted W11-to-iPhone path works.

## Verification evidence

Historical counts in the original report are retained as historical claims, not newly rerun results. The merged snapshot's [frontend QA record](qa/frontend.md) reports 261 backend tests passed and one real-detector integration test skipped, 55 frontend unit tests passed, TypeScript/build success, 13 HTTP checks, and browser workflow checks on a synthetic route. These are software results for the recorded environment; this documentation PR did not rerun them. The root [README](README.md) records local webcam/YOLO measurements and distinguishes them from hosted and physical acceptance.

For direct inspection, reviewers can read the [original Kiro account](https://github.com/adhyannsingal/stride/blob/3e71e21990d2341d937f09192085fbc2144fb786/Kiro_Usage.md), the [historical .kiro commit](https://github.com/adhyannsingal/stride/commit/45e8c095b8679b2feb4529d4bd17f60e4380af93), [PR #2](https://github.com/adhyannsingal/stride/pull/2), the source folders above, and [QA evidence](qa/). A teammate should provide actual Kiro session links or screenshots if available; none are manufactured here.

## Current limits and reproduction

Physical sensor calibration, W11 camera uploads to the hosted backend, motor actuation, iPhone/AirPods audibility, accessible real-world walking tests, and the complete server-authorized speech pipeline remain separate verification or integration tasks. Demo routes must be manually checked before guidance. Missing detections and stale or unknown range data do not establish a clear path.

Follow the root [quick start](README.md#quick-start) for the current model, backend and frontend setup. For focused checks, use the backend's documented Python environment and run pytest from backend_phase3; use the pinned pnpm version, frontend tests and build from frontend. The historical Phase 1–3 commands and counts are in the [original report](https://github.com/adhyannsingal/stride/blob/3e71e21990d2341d937f09192085fbc2144fb786/Kiro_Usage.md).

## Hackachusetts submission check

The [official setup guide](https://massaicoalition.com/hackachusetts/setup/) and [submission rules](https://massaicoalition.com/hackachusetts/submitting-projects/) require a Kiro-built vibe-coded project, a GitHub repository connected through Kiro, and a completed SundAI submission with the correct repository and required project details before the published deadline. They do **not** identify a .kiro directory or a Kiro_Usage.md file as sufficient proof. This page helps reviewers find evidence, but it cannot verify Kiro account activity, the team's Kiro-to-GitHub connection, SundAI fields, submission completion or eligibility. The team must confirm those in Kiro and SundAI.
