import os
import sys

# Windows requires ProactorEventLoop for subprocess support (Playwright)
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
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
    from storage.database import init_db, get_connection, get_workspace
    from scrapers.runner import run_scraping
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    init_db(WORKSPACE)

    scheduler = AsyncIOScheduler()
    conn = get_connection()
    ws = get_workspace(conn)
    conn.close()

    schedule = (ws["scraping_schedule"] if ws and ws["scraping_schedule"]
                else "0 7 * * *")
    parts = schedule.split()
    if len(parts) == 5:
        scheduler.add_job(
            run_scraping,
            CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4]
            ),
            id="scheduled_scraping",
            replace_existing=True,
        )

    scheduler.start()
    app.state.scheduler = scheduler  # Store for potential runtime reschedule
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory="static"), name="static")

from routers import auth, imoveis, scraping, workspace
app.include_router(auth.router)
app.include_router(imoveis.router)
app.include_router(scraping.router)
app.include_router(workspace.router)


@app.get("/")
async def root():
    return RedirectResponse(url="/aluguel")
