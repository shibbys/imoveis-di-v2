import re
from collections import OrderedDict
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from storage.database import (
    get_connection, mark_reviewed, update_schedule, get_workspace,
    get_sites, update_site, get_site_counts, get_last_run_per_base,
)
from routers.auth import require_login

router = APIRouter()
from routers.shared_templates import templates


def _site_display(base: str) -> str:
    return base.replace("_", " ").title()


def _build_site_groups(conn) -> OrderedDict:
    """Group sites by base imobiliária name (stripping _compra/_aluguel suffix)."""
    sites = get_sites(conn)
    counts = get_site_counts(conn)
    last_runs = get_last_run_per_base(conn)
    groups: OrderedDict = OrderedDict()
    for row in sites:
        site = dict(row)
        site["count"] = counts.get(site["name"], 0)
        base = re.sub(r"_(compra|aluguel)$", "", site["name"])
        if base not in groups:
            groups[base] = {
                "base": base,
                "display": _site_display(base),
                "aluguel": [],
                "compra": [],
                "last_run": last_runs.get(base),
            }
        tt = site.get("transaction_type", "")
        if tt in ("aluguel", "compra"):
            groups[base][tt].append(site)
    return groups


@router.get("/configuracoes/site-groups-body", response_class=HTMLResponse)
async def site_groups_body(request: Request):
    """Returns only the <tbody> rows with fresh site counts. Used by SSE done trigger."""
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    site_groups = _build_site_groups(conn)
    conn.close()
    return templates.TemplateResponse(request, "partials/_site_groups_body.html",
                                      {"site_groups": site_groups})


@router.get("/configuracoes/site-row/{base_name}", response_class=HTMLResponse)
async def site_row_get(request: Request, base_name: str):
    """Return a single refreshed <tr> for the configurações table (used by SSE base_done)."""
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    groups = _build_site_groups(conn)
    conn.close()
    group = groups.get(base_name)
    if not group:
        return HTMLResponse(status_code=404)
    return templates.TemplateResponse(request, "partials/_config_site_row.html",
                                      {"group": group})


@router.post("/workspace/reviewed/{tipo}", response_class=HTMLResponse)
async def reviewed(request: Request, tipo: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    if tipo not in ("aluguel", "compra"):
        return HTMLResponse(status_code=400)
    conn = get_connection()
    mark_reviewed(conn, tipo)
    conn.commit()
    conn.close()
    return HTMLResponse(content="")  # HTMX replaces banner with nothing (outerHTML swap)


@router.get("/configuracoes", response_class=HTMLResponse)
async def configuracoes_get(request: Request):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    conn = get_connection()
    ws = get_workspace(conn)
    site_groups = _build_site_groups(conn)
    conn.close()
    return templates.TemplateResponse(request, "configuracoes.html", {
        "active_tab": "configuracoes",
        "username": request.session.get("username"),
        "workspace": ws,
        "site_groups": site_groups,
    })


@router.post("/configuracoes")
async def configuracoes_post(request: Request, schedule: str = Form(...)):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    conn = get_connection()
    update_schedule(conn, schedule)
    conn.commit()
    conn.close()

    # Re-schedule the running APScheduler job immediately
    parts = schedule.strip().split()
    if len(parts) == 5:
        try:
            from apscheduler.triggers.cron import CronTrigger
            from scrapers.runner import run_scraping
            scheduler = request.app.state.scheduler
            scheduler.reschedule_job(
                "scheduled_scraping",
                trigger=CronTrigger(
                    minute=parts[0], hour=parts[1], day=parts[2],
                    month=parts[3], day_of_week=parts[4],
                ),
            )
        except Exception:
            pass  # Job may not exist yet if scheduler failed to start; silently ignore

    return RedirectResponse(url="/configuracoes", status_code=303)


@router.get("/configuracoes/site/{base_name}", response_class=HTMLResponse)
async def site_edit_get(request: Request, base_name: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    groups = _build_site_groups(conn)
    conn.close()
    group = groups.get(base_name)
    if not group:
        return HTMLResponse(status_code=404)
    return templates.TemplateResponse(request, "partials/_config_site_edit.html",
                                      {"group": group})


@router.get("/configuracoes/site/{base_name}/cancel", response_class=HTMLResponse)
async def site_edit_cancel(request: Request, base_name: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    groups = _build_site_groups(conn)
    conn.close()
    group = groups.get(base_name)
    if not group:
        return HTMLResponse(status_code=404)
    return templates.TemplateResponse(request, "partials/_config_site_row.html",
                                      {"group": group})


@router.post("/configuracoes/site/{base_name}", response_class=HTMLResponse)
async def site_edit_post(request: Request, base_name: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    form = await request.form()
    conn = get_connection()
    groups = _build_site_groups(conn)
    group = groups.get(base_name)
    if not group:
        conn.close()
        return HTMLResponse(status_code=404)

    all_sites = group["aluguel"] + group["compra"]
    for site in all_sites:
        name = site["name"]
        new_url = str(form.get(f"url_{name}", site["url"])).strip()
        new_active = f"active_{name}" in form
        update_site(conn, name, new_url, new_active)

    conn.commit()
    # Reload group data after save
    groups = _build_site_groups(conn)
    conn.close()
    group = groups.get(base_name)
    return templates.TemplateResponse(request, "partials/_config_site_row.html",
                                      {"group": group})
