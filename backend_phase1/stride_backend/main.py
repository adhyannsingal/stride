"""FastAPI app factory. Run: uvicorn stride_backend.main:create_app --factory."""

from contextlib import asynccontextmanager
from io import BytesIO
from time import time_ns
from uuid import uuid4

from fastapi import FastAPI, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.security import APIKeyHeader
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from python_multipart.exceptions import MultipartParseError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException, MultiPartParser

from .errors import BackendError, error_response
from .ingestion import IngestionGuard, MULTIPART_OVERHEAD_BYTES
from .models import (
    ErrorResponse, FrameMetadata, FrameReceipt, HealthResponse,
    ReceivedFrameMetadata, TimeResponse,
)
from .settings import Settings
from .store import Frame, LatestFrameStore

device_token_header = APIKeyHeader(name="X-Device-Token", auto_error=False)


def validate_jpeg(data: bytes, max_pixels: int) -> tuple[int, int]:
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise BackendError(422, "invalid_jpeg", "File must contain a complete JPEG image")
    try:
        with Image.open(BytesIO(data), formats=["JPEG"]) as image:
            if image.width * image.height > max_pixels:
                raise BackendError(413, "image_too_large", "Image exceeds the configured pixel limit")
            image.load()  # Decode, rather than trusting a filename or SOI/EOI markers.
            return image.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise BackendError(422, "invalid_jpeg", "File must contain a decodable JPEG image") from None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    store = LatestFrameStore(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        store.clear()

    app = FastAPI(title="STRIDE Backend", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.frame_store = store
    app.add_middleware(IngestionGuard, settings=settings)

    @app.exception_handler(BackendError)
    async def handle_backend_error(request: Request, exc: BackendError):
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def handle_validation_error(request: Request, exc):
        fields = sorted({".".join(str(x) for x in error["loc"]) for error in exc.errors()})
        return error_response(422, "validation_error", "Request fields failed validation", fields)

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException):
        return error_response(exc.status_code, "http_error", "Request could not be processed")

    @app.exception_handler(Exception)
    async def handle_internal_error(request: Request, exc: Exception):
        return error_response(500, "internal_error", "Internal server error")

    @app.get("/health", response_model=HealthResponse)
    async def health():
        return HealthResponse()

    @app.get("/time", response_model=TimeResponse)
    async def server_time():
        from fastapi.responses import JSONResponse
        return JSONResponse(
            TimeResponse(server_ms=time_ns() // 1_000_000).model_dump(),
            headers={"Cache-Control": "no-store"},
        )

    form_schema = FrameMetadata.model_json_schema()
    form_schema["properties"]["file"] = {"type": "string", "format": "binary"}
    form_schema["required"].append("file")
    form_schema["properties"]["sequence"]["description"] = "Strictly increasing per session/device/boot"
    form_schema["properties"]["captured_ms"]["description"] = "Camera time; not trusted for freshness before clock alignment"

    @app.post(
        "/frame", response_model=FrameReceipt, status_code=202,
        dependencies=[Security(device_token_header)],
        responses={code: {"model": ErrorResponse} for code in (400, 401, 409, 413, 415, 422, 429)},
        openapi_extra={"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": form_schema}}}},
    )
    async def upload_frame(request: Request):
        # The guard already bounds the complete body and authenticates it.
        # Keep all parsed files in RAM even when the byte limit is increased.
        parser = MultiPartParser(
            headers=request.headers, stream=request.stream(),
            max_files=1, max_fields=len(FrameMetadata.model_fields), max_part_size=1024,
        )
        parser.spool_max_size = settings.max_frame_bytes + MULTIPART_OVERHEAD_BYTES + 1
        try:
            form = await parser.parse()
        except (MultiPartException, MultipartParseError, ValueError):
            raise BackendError(400, "invalid_multipart", "Malformed multipart body or too many fields/files") from None

        try:
            if len(form.multi_items()) != len(form):
                raise BackendError(422, "validation_error", "Duplicate form fields are not allowed")
            upload = form.get("file")
            if not isinstance(upload, UploadFile):
                raise BackendError(422, "validation_error", "A JPEG file field named file is required")
            metadata = FrameMetadata.model_validate({k: v for k, v in form.items() if k != "file"})
            if upload.content_type != "image/jpeg":
                raise BackendError(415, "unsupported_media_type", "The file Content-Type must be image/jpeg")
            data = await upload.read(settings.max_frame_bytes + 1)
            if len(data) > settings.max_frame_bytes:
                raise BackendError(413, "frame_too_large", "JPEG exceeds STRIDE_MAX_FRAME_BYTES")
            width, height = await run_in_threadpool(validate_jpeg, data, settings.max_image_pixels)
            received = ReceivedFrameMetadata(
                **metadata.model_dump(), receipt_id=str(uuid4()),
                received_ms=request.scope["stride.received_ms"], size_bytes=len(data),
                width=width, height=height,
            )
            frame = Frame(data, received, request.scope["stride.received_monotonic_ms"])
            replaced = store.put(frame)
            return FrameReceipt(**received.model_dump(), replaced_pending=replaced)
        finally:
            await form.close()

    return app
