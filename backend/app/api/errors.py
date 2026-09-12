"""Structured error responses: {code, message, details, request_id} - never a
secret or provider payload, per specs/API_SPEC.md and specs/SECURITY.md."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import ErrorResponse


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        body = ErrorResponse(
            code=f"http_{exc.status_code}",
            message=str(exc.detail),
            details=None,
            request_id=_request_id(request),
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        body = ErrorResponse(
            code="validation_error",
            message="invalid request",
            details={"errors": exc.errors()},
            request_id=_request_id(request),
        )
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        body = ErrorResponse(
            code="internal_error",
            message="an unexpected error occurred",
            details=None,
            request_id=_request_id(request),
        )
        return JSONResponse(status_code=500, content=body.model_dump())
