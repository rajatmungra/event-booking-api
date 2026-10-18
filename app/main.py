import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import SessionDep
from app.api.routes import auth, bookings, events, seats, users
from app.core.exceptions import AppError
from app.core.logging import request_id_var, setup_logging

setup_logging()
logger = logging.getLogger("app")

app = FastAPI(title="Event Booking API")
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(events.router)
app.include_router(seats.router)
app.include_router(bookings.router)

# Accept a client's X-Request-ID only if it's short and harmless to put in logs and headers.
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
        headers=headers,
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    # Middleware wraps every request: runs code before the route and after the response.
    incoming = request.headers.get("X-Request-ID", "")
    request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            # A bug: log the full traceback, but tell the client nothing about internals.
            logger.exception("unhandled error")
            response = error_response(500, "INTERNAL_ERROR", "Something went wrong.")
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request",
            extra={
                "fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                }
            },
        )
        return response
    finally:
        request_id_var.reset(token)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    headers = dict(exc.headers)
    # 401 responses must tell the client which auth scheme to use.
    if exc.status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return error_response(exc.status_code, exc.code, exc.message, exc.details, headers)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Keep only loc/msg/type: the raw "input" could echo a password back to the client.
    errors = [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return error_response(422, "VALIDATION_ERROR", "Invalid request.", {"errors": errors})


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Errors raised by the framework itself, e.g. unknown URL (404) or wrong method (405).
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, code, str(exc.detail), headers=exc.headers)


@app.get("/health")
async def health(session: SessionDep):
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        # asyncpg raises OSError (e.g. ConnectionRefusedError) when the server is unreachable.
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
