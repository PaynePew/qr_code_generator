import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .database import engine
from .link_state import LinkAlreadyDeletedError, LinkNotFoundError
from .models import Base
from .router import router, redirect_router

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("SECRET"):
        raise RuntimeError("SECRET environment variable must be set")
    if not os.environ.get("BASE_URL"):
        raise RuntimeError("BASE_URL environment variable must be set")
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://localhost:\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LinkNotFoundError)
async def _link_not_found(_: Request, exc: LinkNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Token not found"})


@app.exception_handler(LinkAlreadyDeletedError)
async def _link_already_deleted(_: Request, exc: LinkAlreadyDeletedError) -> JSONResponse:
    return JSONResponse(status_code=410, content={"detail": "Link is deleted"})


app.include_router(router)
app.include_router(redirect_router)
