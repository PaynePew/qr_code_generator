import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from .database import engine
from .models import Base
from .router import router

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
app.include_router(router)
