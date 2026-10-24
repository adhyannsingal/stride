"""Session-authorized control and polling routes."""

from fastapi import APIRouter, Request, Response, Security
from fastapi.security import APIKeyCookie, APIKeyHeader

from .auth import COOKIE_NAME, SessionAuth
from .models import (
    ErrorResponse, Identifier, SessionAuthResponse, SessionCredentials, StatusResponse,
    VisionAction, VisionControlResponse, VisionLatest,
)
from .store import LatestFrameStore
from .worker import InferenceWorker

session_header = APIKeyHeader(name="X-Session-Token", auto_error=False, scheme_name="SessionToken")
session_cookie = APIKeyCookie(name=COOKIE_NAME, auto_error=False, scheme_name="SessionCookie")


def create_vision_router(store: LatestFrameStore, worker: InferenceWorker, auth: SessionAuth) -> APIRouter:
    router = APIRouter(responses={code: {"model": ErrorResponse} for code in (401, 403, 409, 422, 429, 503)})
    authorization = [Security(session_header), Security(session_cookie)]

    @router.post("/auth/session", response_model=SessionAuthResponse)
    async def login(request: Request, response: Response, credentials: SessionCredentials):
        return auth.login(request, response, credentials)

    @router.post("/vision", response_model=VisionControlResponse, dependencies=authorization)
    async def control(request: Request, response: Response, action: VisionAction):
        auth.authorize(request, action.session_id)
        result = store.control(action)
        worker.notify()
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.get("/vision/latest", response_model=VisionLatest, dependencies=authorization)
    async def latest(request: Request, response: Response, session_id: Identifier):
        auth.authorize(request, session_id)
        response.headers["Cache-Control"] = "no-store"
        return store.snapshot(session_id)

    @router.get("/status", response_model=StatusResponse, dependencies=authorization)
    async def status(request: Request, response: Response, session_id: Identifier):
        auth.authorize(request, session_id)
        response.headers["Cache-Control"] = "no-store"
        return StatusResponse(vision=store.snapshot(session_id))

    return router
