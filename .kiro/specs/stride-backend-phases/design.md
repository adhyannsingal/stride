# Implemented design reference

This retrospective design records architecture visible in the repository. It is not a reconstructed Kiro conversation.

## Phase 1

FastAPI receives a multipart upload behind authentication and request-size guards. Pydantic validates metadata; Pillow verifies decodable JPEG content. A receipt binds bytes to session/device/boot/frame/sequence/source identity. The latest-frame store replaces pending work instead of growing a queue and uses monotonic receipt time for expiry. A detector protocol supplies a clean integration boundary so the API can run without model weights.

The engineering tradeoff is bounded latency and memory instead of processing every frame. This matters because an old observation may be misleading even if its classification is correct. Upload acceptance proves ingestion only, not successful recognition.

## Phase 2

A configured detector factory is loaded during application assembly. A bounded worker orchestrates inference away from the event loop. Vision generations invalidate work across lifecycle transitions; source revisions distinguish producer changes. A result can publish only while its identity and age remain valid.

Session authentication uses secrets separate from camera ingestion. Signed HttpOnly cookies, expiry, session checks and explicit origins support browser access. Idempotent controls permit retries after uncertain delivery without duplicating a transition. State and inference remain process-local, so the supported deployment uses one process/replica.

## Phase 3

SQLite stores persistent route and memory state. Navigation transitions and idempotency records keep confirmed progress consistent, while expected revisions reject stale actions. Guidance events carry identity and expiration so playback can be invalidated after route changes. Restart recovery preserves history while requiring explicit human resumption.

Sightings use stable tracked-object identity, cooldowns and bounded retention. They retain original timestamps and last-confirmed-checkpoint context. No object box becomes a world coordinate, measured distance or autonomous turn instruction.

## Frontend and Phase 4 seams

The frontend API adapter speaks the backend's real contracts through a same-origin development proxy. Separate controllers manage browser capture, polling and speech. Device integration adds authenticated telemetry, conservative holds and expiring one-shot motor commands without replacing the independent firmware alert loop.

The practical workflow is inspect → make a small change → review its diff → run relevant checks → hand off. Repository inspection establishes implemented behavior; team reports establish which tools assisted development. Neither proves physical acceptance.
