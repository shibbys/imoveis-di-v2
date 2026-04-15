import asyncio
import json
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse
from routers.auth import require_login
from scrapers.runner import run_scraping, get_event_queue, is_running, get_running_info
from storage.database import get_connection, get_sites, get_last_run

router = APIRouter()
templates = Jinja2Templates(directory="templates")

_LOG_TABLE_HEADER = """
<table class="w-full text-sm border-collapse">
  <thead>
    <tr class="text-left text-gray-500 text-xs uppercase tracking-wide border-b border-gray-700">
      <th class="py-1.5 px-3 font-medium w-16">Hora</th>
      <th class="py-1.5 px-3 font-medium">Imobili&#225;ria</th>
      <th class="py-1.5 px-3 font-medium">Aluguel</th>
      <th class="py-1.5 px-3 font-medium">Compra</th>
      <th class="py-1.5 px-3 font-medium w-24">Status</th>
    </tr>
  </thead>
  <tbody id="scraping-log-body"></tbody>
</table>
"""

_SSE_HTML = '<p id="scraping-live-status" class="text-xs text-gray-500">Iniciando...</p>'


@router.post("/scraping/trigger", response_class=HTMLResponse)
async def trigger_scraping(request: Request, background_tasks: BackgroundTasks):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    if is_running():
        info = get_running_info()
        detail = f" ({info['label']} — {info['elapsed']})" if info else ""
        return HTMLResponse(content=f'<p class="text-yellow-400 text-xs">Scraping j&#225; em execu&#231;&#227;o{detail}</p>')
    form = await request.form()
    force_images = form.get("force_images") in ("1", "on", "true")
    conn = get_connection()
    all_sites = [dict(r) for r in get_sites(conn, active_only=True)]
    conn.close()
    if force_images:
        for s in all_sites:
            s["force_images"] = True
    background_tasks.add_task(run_scraping, sites_config=all_sites)
    return HTMLResponse(content=_SSE_HTML)


@router.post("/scraping/trigger-sites", response_class=HTMLResponse)
async def trigger_scraping_sites(request: Request, background_tasks: BackgroundTasks):
    """Trigger scraping for a specific site or transaction_type subset."""
    if not require_login(request):
        return HTMLResponse(status_code=401)
    if is_running():
        info = get_running_info()
        detail = f" ({info['label']} — {info['elapsed']})" if info else ""
        return HTMLResponse(content=f'<p class="text-yellow-400 text-xs">Scraping j&#225; em execu&#231;&#227;o{detail}</p>')
    form = await request.form()
    site_name = str(form.get("site_name", "")).strip()
    transaction_type = str(form.get("transaction_type", "")).strip()
    force_images = form.get("force_images") in ("1", "on", "true")

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

    if force_images:
        for s in sites:
            s["force_images"] = True

    background_tasks.add_task(run_scraping, sites_config=sites)
    return HTMLResponse(content=_SSE_HTML)


@router.get("/scraping/status", response_class=HTMLResponse)
async def scraping_status(request: Request):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    info = get_running_info()
    if info:
        return HTMLResponse(
            content=f'<p class="text-yellow-400 text-xs">&#9654; Scraping em execu&#231;&#227;o: {info["label"]} — {info["elapsed"]}</p>'
        )
    return HTMLResponse(content="")


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
                yield {"data": msg}
                # Detect completion from the structured event
                try:
                    if json.loads(msg).get("type") == "done":
                        break
                except (json.JSONDecodeError, AttributeError):
                    pass
            except asyncio.TimeoutError:
                yield {"data": ""}  # keepalive ping

    return EventSourceResponse(event_generator())


@router.get("/scraping/last-run", response_class=HTMLResponse)
async def scraping_last_run(request: Request):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    run = get_last_run(conn)
    conn.close()
    return templates.TemplateResponse(
        request, "partials/_scraping_log_table.html", {"run": run}
    )
