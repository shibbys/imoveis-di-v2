import asyncio
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from routers.auth import require_login
from scrapers.runner import run_scraping, get_event_queue, is_running
from storage.database import get_connection, get_sites

router = APIRouter()

_SSE_HTML = """
    <div hx-ext="sse"
         sse-connect="/scraping/stream"
         sse-swap="message"
         hx-target="this"
         hx-swap="beforeend"
         class="text-green-400 text-xs space-y-0.5">
      <p class="text-gray-400">Iniciando scraping...</p>
    </div>
"""


@router.post("/scraping/trigger", response_class=HTMLResponse)
async def trigger_scraping(request: Request, background_tasks: BackgroundTasks):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    if is_running():
        return HTMLResponse(content='<p class="text-yellow-400 text-xs">Scraping já em execução...</p>')
    background_tasks.add_task(run_scraping)
    return HTMLResponse(content=_SSE_HTML)


@router.post("/scraping/trigger-sites", response_class=HTMLResponse)
async def trigger_scraping_sites(request: Request, background_tasks: BackgroundTasks):
    """Trigger scraping for a specific site or transaction_type subset."""
    if not require_login(request):
        return HTMLResponse(status_code=401)
    if is_running():
        return HTMLResponse(content='<p class="text-yellow-400 text-xs">Scraping já em execução...</p>')
    form = await request.form()
    site_name = str(form.get("site_name", "")).strip()
    transaction_type = str(form.get("transaction_type", "")).strip()

    conn = get_connection()
    all_sites = [dict(r) for r in get_sites(conn, active_only=True)]
    conn.close()

    if site_name:
        sites = [s for s in all_sites if s["name"] == site_name]
    elif transaction_type in ("aluguel", "compra"):
        sites = [s for s in all_sites if s["transaction_type"] == transaction_type]
    else:
        sites = all_sites

    if not sites:
        return HTMLResponse(content='<p class="text-red-400 text-xs">Nenhum site encontrado.</p>')

    background_tasks.add_task(run_scraping, sites_config=sites)
    return HTMLResponse(content=_SSE_HTML)


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
                    yield {
                        "data": (
                            "<p class='text-gray-400'>✓ Concluído</p>"
                            "<span hx-get='/configuracoes/site-groups-body'"
                            "      hx-trigger='load'"
                            "      hx-target='#site-groups-body'"
                            "      hx-swap='innerHTML'></span>"
                        )
                    }
                    break
                yield {"data": f"<p>{msg}</p>"}
            except asyncio.TimeoutError:
                yield {"data": ""}  # keepalive ping

    return EventSourceResponse(event_generator())
