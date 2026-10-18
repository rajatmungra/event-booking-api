from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import SessionDep
from app.api.routes import auth, events, users
from app.core.exceptions import AppError

app = FastAPI(title="Event Booking API")
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(events.router)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    # 401 responses must tell the client which auth scheme to use.
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        headers=headers,
    )


@app.get("/health")
async def health(session: SessionDep):
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        # asyncpg raises OSError (e.g. ConnectionRefusedError) when the server is unreachable.
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
