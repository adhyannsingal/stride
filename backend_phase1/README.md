# STRIDE backend — Milestone 1

Python FastAPI ingestion service. No model is required to start it. The app exposes
`GET /health`, `GET /time`, `POST /frame`, and Swagger at `/docs`.

## Run

Tested with Python 3.13. Use Python 3.11 or newer.

```sh
cd ~/Desktop/LeHacks/stride/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

For local development only, edit `.env` to set `STRIDE_LOCAL_DEV=true`. Then:

```sh
uvicorn stride_backend.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
python -m pytest -q
```

Open `http://127.0.0.1:8000/docs`. For token-protected development, set a real
`STRIDE_DEVICE_TOKEN` in `.env` and use Swagger's **Authorize** button.

For hosting, install `requirements.txt`, set `STRIDE_DEVICE_TOKEN` through the
host's secret settings, keep `STRIDE_LOCAL_DEV=false`, and use:

```sh
uvicorn stride_backend.main:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
```

Use the host's HTTPS ingress. This in-memory milestone needs **one process and
one replica**: multiple workers/replicas would have separate frame stores and
sequence histories. No hostname or hosting provider is hardcoded. Production
startup fails if no device token is configured. Do not put this camera token in
the phone frontend; phone session/cookie authentication is a later milestone.

## Upload contract

Send one file part named `file` with `Content-Type: image/jpeg`. Required text
parts: `session_id`, `device_id`, `boot_id`, `frame_id`, `sequence`, `captured_ms`,
`source`. Identifiers are trimmed, nonempty and at most 128 characters. Sequence
and capture time are nonnegative integers. Source is `real`, `simulated`, or
`fixture`; availability is not a source. Optional `origin` defaults to
`unspecified`, and `source_revision` defaults to `0`.

Example using a test image and a token exported into the shell securely:

```sh
curl http://127.0.0.1:8000/frame \
  -H "X-Device-Token: ${STRIDE_DEVICE_TOKEN}" \
  -F 'file=@/path/to/test.jpg;type=image/jpeg' \
  -F session_id=demo-1 -F device_id=camera-1 -F boot_id=boot-1 \
  -F frame_id=frame-1 -F sequence=1 -F captured_ms=42 -F source=fixture \
  -F origin=test-file -F source_revision=0
```

Successful uploads return **202 Accepted**, echoing identity/provenance plus
`receipt_id`, server epoch `received_ms`, `size_bytes`, `width`, `height`,
`status=accepted`, `replaced_pending`, `freshness_basis=server_receipt`, and
`camera_clock_aligned=false`. Each accepted frame receives a unique receipt ID.
`GET /time` returns `{"server_ms": <epoch milliseconds>}` with caching disabled.

All errors use `{"error":{"code":"...","message":"...","fields":[]}}`.
Missing/invalid metadata or invalid JPEG: 422; missing/incorrect token: 401;
duplicate/regressing sequence or source revision: 409; oversized upload/image:
413; wrong media type: 415; malformed multipart: 400; store capacity: 429.
Increment sequence on every upload; a new device boot gets a new `boot_id`.

## Bounds, privacy and freshness

Defaults: 512 KiB per JPEG, 4 million decoded pixels, eight sessions, and sixteen
device/boot sequence histories per session. The entire multipart request is
limited to the JPEG limit plus 16 KiB, including requests without Content-Length.
Authentication runs before body reads. Multipart files stay in RAM and close
after parsing; images are never written to disk or logged. JPEG validation
decodes the image off the HTTP event loop. Bytes and orientation remain intact.

Each session holds one newest pending frame and at most one claimed inference
frame. New uploads replace pending frames, without a work queue. Sequence
history survives frame consumption and image expiry. At capacity, new sessions
or device/boot histories receive 429; active histories are not silently evicted.
Inactive sessions expire after five minutes on the next store operation, once
their inference claim is released. Replay history is process-local and expires
with the session; clients should use a new session ID after a long disconnect.

Live frames/results expire after **1,000 ms** using monotonic server receipt
time, independently of `captured_ms`. A configured freshness limit may be
stricter, never greater than 1,000 ms. This bounds time since server receipt;
end-to-end capture age cannot be verified until clock offset/RTT alignment is
implemented. A camera/source switch must increment `source_revision`.

## Detector interface

Implement the protocol in `stride_backend/detector.py`:

```python
class Detector(Protocol):
    async def detect(self, frame: Frame) -> DetectionBatch: ...
```

`Frame` supplies `jpeg: bytes`, `metadata: ReceivedFrameMetadata`, and an internal
monotonic receipt timestamp. Return `DetectionBatch(frame=frame.metadata,
completed_ms=<server epoch milliseconds>, provider="yolo", objects=<detections>)`.
Preserve the entire metadata object, including receipt/session/device/boot/frame
identity, sequence, provenance and source revision.

Each `Detection` contains `label: str`, `score: float` in [0,1], normalized
image-relative `bbox: (xmin, ymin, xmax, ymax)` in [0,1], and optional
`track_id: str`. Coordinates must have positive width/height. At most 300 objects
are allowed per batch. Stable tracks and speech policy belong to the later live
vision integration.

The integration worker uses this seam, with **one job per session**:

```python
store = app.state.frame_store
frame = store.take_latest(session_id)  # None if absent, stale, or already claimed
if frame is not None:
    try:
        batch = await detector.detect(frame)
        published = store.publish_detections(batch)
    finally:
        store.finish(frame)  # Release even if inference fails or is cancelled
```

Run blocking model inference off the HTTP event loop; load the model once.
Publication returns `False` for a mismatched receipt, stale result, duplicate
publication, or changed source. A still-fresh claimed frame can publish while
newer frames wait. `store.latest_detections(session_id)` returns a fresh batch
or `None`; reading it also enforces expiry. There is no model loader, fake live
output, automatic worker, or public detection endpoint in this milestone.

## Verification

Verification result: **58 passed** on Python 3.13; `pip check` reports no broken
requirements. Starlette emits one upstream deprecation warning about its httpx
test adapter. Tests cover endpoint/schema behavior, validation/authentication, upload bounds,
sequence order, replacement, bounded capacity, freshness, and detector identity.
In this execution environment, dependency installation succeeded via verified
PyPI wheels; normal pip network resolution failed. Uvicorn reached application
startup but both TCP and Unix socket binding were denied by the environment.
The in-process HTTP tests pass; a socket-level smoke test must run in an
unrestricted local terminal or the chosen host before deployment is claimed.

This milestone adds no frontend, firmware, YOLO implementation, database, telemetry,
or route guidance. Hosted live rate/latency and real hardware are not validated.
