from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

app = FastAPI(title="Event Booking API")


@app.get("/health")
async def health(session: Annotated[AsyncSession, Depends(get_session)]):
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        # asyncpg raises OSError (e.g. ConnectionRefusedError) when the server is unreachable.
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
