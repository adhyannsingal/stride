"""Consistent error envelopes without echoing request bodies or credentials."""

from fastapi.responses import JSONResponse

from .models import ErrorDetail, ErrorResponse


class BackendError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def error_response(status_code: int, code: str, message: str, fields=()) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, fields=tuple(fields)))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))
