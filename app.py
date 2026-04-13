import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

WORKSPACE = os.getenv("WORKSPACE", "workspaces/imoveis.db")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-in-production")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Will be expanded in later tasks to init DB and start scheduler
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return RedirectResponse(url="/aluguel")
