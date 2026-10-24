---
inclusion: always
---
# Structure and ownership

Inspect README.md, applicable AGENTS.md files, handoffs and current Git state before editing. Use an isolated worktree for integration. Preserve uncommitted teammate work. Never infer authorization to push, merge, force-update or delete branches.

| Path | Responsibility |
|---|---|
| backend_phase1/ | Historical ingestion milestone: validation, bounded frame store, detector seam |
| backend_phase2/ | Historical continuous vision/session-auth milestone |
| backend_phase3/ | Current backend: Phase 3 SQLite/routes plus Phase 4 controller integration |
| app/vision/ | Vision teammate's model adapter, tracking and memory bridge |
| frontend/ | Phone web application; keep API, controllers, policy and UI concerns separate |
| firmware/ | Hardware teammate's camera and feedback firmware |
| models/manifest.json | Intended model metadata and checksums; weights excluded from Git |
| contracts/, handoff/, qa/ | Shared contracts, ownership, reproducible evidence |
| web/ | Earlier browser client; distinguish it from the current frontend |

Do not copy new features into all historical backend folders. Do not modify backend or firmware merely to conceal a frontend mismatch. Fix the contract at its owning layer and document any coordinated change.

The existing frontend tracks some normal Git PNG blobs under broad LFS rules. Inspect image attributes and bytes before staging; never blindly stage unexpected binary modifications. A prepared exact-path exemption exists in the separate Phase 5 follow-up patch; check whether it has landed before applying another fix.
