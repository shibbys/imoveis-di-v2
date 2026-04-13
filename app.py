import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

WORKSPACE = os.getenv("WORKSPACE", "workspaces/imoveis.db")
SESSION_SECRET = os.getenv("SESSION_SECRET")
if not SESSION_SECRET:
    if os.getenv("ENV", "development") == "production":
        import sys
        sys.exit("ERROR: SESSION_SECRET environment variable must be set in production")
    SESSION_SECRET = "dev-secret-change-in-production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from storage.database import init_db
    init_db(WORKSPACE)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory="static"), name="static")

from routers import auth
app.include_router(auth.router)


@app.get("/")
async def root():
    return RedirectResponse(url="/aluguel")


@app.get("/aluguel", response_class=HTMLResponse)
async def aluguel_stub(request: Request):
    from routers.auth import require_login
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    return HTMLResponse("<html><body>aluguel stub</body></html>")
