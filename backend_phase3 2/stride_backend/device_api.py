"""Authenticated hardware APIs and a fixed supplemental freshness monitor."""

import asyncio

from fastapi import APIRouter, Request, Response, Security
from fastapi.security import APIKeyHeader

from .device_models import AckResponse, CommandAck, CommandPoll, DevicePair, DeviceStatus, PairResponse, Telemetry, TelemetryResponse
from .errors import BackendError
from .models import ErrorResponse, Identifier
from .vision import session_cookie, session_header

controller_header = APIKeyHeader(name='X-Device-Token', auto_error=False, scheme_name='ControllerToken')


def create_device_router(database, service, controller_auth, session_auth):
    router = APIRouter(responses={code: {'model': ErrorResponse} for code in (400,401,403,404,409,413,415,422,429,503)})

    @router.post('/device/pair', response_model=PairResponse, dependencies=[Security(session_header), Security(session_cookie)])
    async def pair(request: Request, response: Response, body: DevicePair):
        session_auth.authorize(request, body.session_id)
        response.headers['Cache-Control'] = 'no-store'
        return await database.run(service.pair, body.device_id, body.session_id)

    @router.post('/telemetry', response_model=TelemetryResponse, dependencies=[Security(controller_header)])
    @router.post('/device/telemetry', response_model=TelemetryResponse, dependencies=[Security(controller_header)], include_in_schema=False)
    async def telemetry(request: Request, response: Response, body: Telemetry):
        if request.scope['stride.controller_id'] != body.device_id:
            raise BackendError(403, 'device_access_denied', 'Telemetry identity does not match its credential')
        response.headers['Cache-Control'] = 'no-store'
        return await database.run(service.ingest, body, request.scope['stride.controller_received_ms'], request.scope['stride.controller_received_mono'])

    async def poll_impl(request, response, device_id):
        controller_auth.authenticate(request.headers, device_id)
        response.headers['Cache-Control'] = 'no-store'
        return await database.run(service.poll, device_id)

    @router.get('/devices/{device_id}/commands', response_model=CommandPoll, dependencies=[Security(controller_header)])
    async def path_commands(request: Request, response: Response, device_id: Identifier):
        return await poll_impl(request, response, device_id)

    @router.get('/device/commands', response_model=CommandPoll, dependencies=[Security(controller_header)], include_in_schema=False)
    async def query_commands(request: Request, response: Response, device_id: Identifier):
        return await poll_impl(request, response, device_id)

    async def ack_impl(request, response, body):
        if request.scope['stride.controller_id'] != body.device_id:
            raise BackendError(403, 'device_access_denied', 'Acknowledgment identity does not match its credential')
        response.headers['Cache-Control'] = 'no-store'
        return await database.run(service.acknowledge, body)

    @router.post('/device/ack', response_model=AckResponse, dependencies=[Security(controller_header)])
    async def acknowledge(request: Request, response: Response, body: CommandAck):
        return await ack_impl(request, response, body)

    @router.post('/devices/{device_id}/ack', response_model=AckResponse, dependencies=[Security(controller_header)])
    async def path_acknowledge(request: Request, response: Response, device_id: Identifier, body: CommandAck):
        if body.device_id != device_id:
            raise BackendError(403, 'device_access_denied', 'Path and acknowledgment device IDs must match')
        return await ack_impl(request, response, body)

    @router.get('/device/status', response_model=DeviceStatus, dependencies=[Security(controller_header), Security(session_header), Security(session_cookie)])
    async def status(request: Request, response: Response, device_id: Identifier, session_id: Identifier | None = None):
        if request.headers.get('x-device-token') is not None or request.headers.get('x-device-id') is not None:
            controller_auth.authenticate(request.headers, device_id)
        else:
            owner = service.settings.controller_sessions.get(device_id)
            if owner is None or (session_id is not None and session_id != owner):
                raise BackendError(403, 'device_access_denied', 'Device is not provisioned for this session')
            session_auth.authorize(request, owner)
        response.headers['Cache-Control'] = 'no-store'
        return await database.run(service.status, device_id)

    return router


class DeviceMonitor:
    def __init__(self, database, service):
        self.database, self.service = database, service
        self.task = None
        self.last_error = None
        self.stop = None

    async def start(self):
        if not self.service.enabled:
            return
        self.stop = asyncio.Event()
        self.task = asyncio.create_task(self._run(), name='stride-device-monitor')

    async def _run(self):
        while not self.stop.is_set():
            try:
                await asyncio.wait_for(self.stop.wait(), self.service.settings.device_monitor_interval_ms / 1000)
            except TimeoutError:
                try:
                    await self.database.run(self.service.maintenance)
                    self.last_error = None
                except BackendError:
                    self.last_error = 'device_monitor_unavailable'

    async def close(self):
        if self.task:
            self.stop.set()
            await self.task
