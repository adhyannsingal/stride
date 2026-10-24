"""Mount once. Backend supplies canonical auth/schema/idempotency/event bridge."""
from typing import Protocol
from fastapi import APIRouter, HTTPException, Request
from .service import VisionService


class VisionAPI(Protocol):
    async def control(self, request: Request, vision: VisionService) -> dict:
        """Validate shared schema/auth/binding; dedup action ID; call control; decorate."""
        ...

    async def latest(self, request: Request, vision: VisionService) -> dict:
        """Validate UI auth/session; snapshot; add shared seq + authorized speech."""
        ...


router = APIRouter()


def _bridge(request):
    bridge = getattr(request.app.state,'vision_api',None)
    vision = getattr(request.app.state,'vision',None)
    if bridge is None or vision is None:
        raise HTTPException(503, 'Canonical vision API adapter not mounted')
    return bridge,vision


@router.post('/vision')
async def control(request: Request):
    bridge,vision = _bridge(request)
    return await bridge.control(request,vision)


@router.get('/vision/latest')
async def latest(request: Request):
    bridge,vision = _bridge(request)
    return await bridge.latest(request,vision)
