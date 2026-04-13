import asyncio
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from routers.auth import require_login
from scrapers.runner import run_scraping, get_event_queue, is_running

router = APIRouter()


@router.post("/scraping/trigger", response_class=HTMLResponse)
async def trigger_scraping(request: Request, background_tasks: BackgroundTasks):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    if is_running():
        return HTMLResponse(
            content='<p class="text-yellow-400 text-xs">Scraping já em execução...</p>'
        )
    background_tasks.add_task(run_scraping)
    return HTMLResponse(content="""
        <div hx-ext="sse"
             sse-connect="/scraping/stream"
             sse-swap="message"
             hx-target="this"
             hx-swap="beforeend"
             class="text-green-400 text-xs space-y-0.5">
          <p class="text-gray-400">Iniciando scraping...</p>
        </div>
    """)


@router.get("/scraping/stream")
async def scraping_stream(request: Request):
    if not require_login(request):
        return HTMLResponse(status_code=401)

    queue = get_event_queue()

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                if msg == "__DONE__":
                    yield {"data": "<p class='text-gray-400'>✓ Concluído</p>"}
                    break
                yield {"data": f"<p>{msg}</p>"}
            except asyncio.TimeoutError:
                yield {"data": ""}  # keepalive ping

    return EventSourceResponse(event_generator())
