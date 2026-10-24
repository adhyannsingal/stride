# STRIDE — Kiro project context

Created 2026-10-24 from the existing STRIDE implementation. These files consolidate project knowledge for future Kiro sessions; they are not a historical Kiro activity log.

## Contents

- `steering/product.md`: purpose, user experience, safety boundaries.
- `steering/tech.md`: actual stack, API conventions and verification commands.
- `steering/structure.md`: repository ownership and phase map.
- `steering/reliability.md`: invariants for camera, navigation, speech and devices.
- `specs/stride-backend-phases/requirements.md`: retrospective Phase 1–3 requirements.
- `specs/stride-backend-phases/design.md`: implemented architecture and tradeoffs.
- `specs/stride-backend-phases/tasks.md`: review tasks for continued development.
Copy this `.kiro` directory into the STRIDE repository root, preserving any existing teammate files. Open that repository in Kiro or run `kiro-cli chat` there. Ask Kiro to read the steering files, inspect the current source, and choose the next task from the review list. File presence alone does not prove a particular Kiro feature was used historically.

Suggested next prompt:

> Read .kiro/steering and .kiro/specs/stride-backend-phases. Verify the current branch and dirty files, then inspect the actual backend and frontend contracts before editing. Preserve teammate work and the landing-page animation. Address one concrete integration issue, run the relevant tests, and report the actual results. Do not push or merge without authorization.

Kiro documents workspace guidance in `.kiro/steering/`: https://kiro.dev/docs/steering/

These documents add no hooks, MCP servers, credentials, dependencies or executable agents. No prior use of Crew, Powers, Web, hooks or MCP is claimed.
