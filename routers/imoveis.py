import re
import folium
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from storage.database import (
    get_connection, get_imoveis, get_imovel, get_imovel_images,
    get_imovel_price_history, update_imovel_status, update_imovel_fields,
    log_activity, get_last_activity, get_distinct_values,
    get_changes_since_review, mark_reviewed, get_runs, get_run,
)
from routers.auth import require_login

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _site_display_name(name: str) -> str:
    """Convert scraper ID (e.g. 'felippe_alfredo_compra') to display name ('Felippe Alfredo')."""
    name = re.sub(r"_(compra|aluguel)$", "", name)
    return name.replace("_", " ").title()


templates.env.filters["site_name"] = _site_display_name


def _format_duration(seconds) -> str:
    """Convert seconds to a human-readable duration string (e.g. '1h 4m 32s')."""
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return "—"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


templates.env.filters["format_duration"] = _format_duration

STATUSES = [
    "Novo", "Em análise", "Interessante", "Visita agendada",
    "Visitado", "Não tem interesse", "Descartado"
]

STATUS_COLORS = {
    "Novo": "blue", "Em análise": "orange", "Interessante": "green",
    "Visita agendada": "purple", "Visitado": "darkgreen",
    "Não tem interesse": "gray", "Descartado": "red",
}



def _filter_options(conn, tipo: str) -> dict:
    return {
        "sites": get_distinct_values(conn, tipo, "source_site"),
        "statuses": get_distinct_values(conn, tipo, "status"),
        "neighborhoods": get_distinct_values(conn, tipo, "neighborhood"),
        "categories": get_distinct_values(conn, tipo, "category"),
    }


def _listing_page(request: Request, tipo: str):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    conn = get_connection()
    changes = get_changes_since_review(conn, tipo)
    options = _filter_options(conn, tipo)
    conn.close()
    template = "aluguel.html" if tipo == "aluguel" else "compra.html"
    return templates.TemplateResponse(request, template, {
        "active_tab": tipo,
        "tipo": tipo,
        "username": request.session.get("username"),
        "changes": changes,
        "filters": {"status": "Novo"},
        "filter_options": options,
    })


@router.get("/aluguel", response_class=HTMLResponse)
async def aluguel(request: Request):
    return _listing_page(request, "aluguel")


@router.get("/compra", response_class=HTMLResponse)
async def compra(request: Request):
    return _listing_page(request, "compra")


@router.get("/mapa", response_class=HTMLResponse)
async def mapa(request: Request):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    conn = get_connection()
    imoveis_aluguel = get_imoveis(conn, "aluguel")
    imoveis_compra = get_imoveis(conn, "compra")

    # Fetch cover images for all mapped properties in one query
    all_imoveis = list(imoveis_aluguel) + list(imoveis_compra)
    mapped_ids = [im["id"] for im in all_imoveis if im["lat"] and im["lng"]]
    covers: dict = {}
    if mapped_ids:
        ph = ",".join("?" * len(mapped_ids))
        rows = conn.execute(
            f"SELECT imovel_id, url FROM imovel_imagens WHERE position=0 AND imovel_id IN ({ph})",
            mapped_ids,
        ).fetchall()
        covers = {r["imovel_id"]: r["url"] for r in rows}
    conn.close()

    m = folium.Map(location=[-29.6167, -51.0833], zoom_start=14)

    for im in all_imoveis:
        if not (im["lat"] and im["lng"]):
            continue
        tipo = im["transaction_type"]
        color = "blue" if tipo == "aluguel" else "red"
        price_str = f'R$ {im["price"]:,.0f}'.replace(",", ".") if im["price"] else "—"
        tipo_label = "Aluguel" if tipo == "aluguel" else "Compra"
        title = im["title"] or im["category"] or "Imóvel"

        cover_url = covers.get(im["id"], "")
        img_html = (
            f'<img src="{cover_url}" style="width:220px;height:130px;'
            f'object-fit:cover;border-radius:4px;margin-bottom:6px;display:block;">'
            if cover_url else ""
        )
        popup_html = (
            f'{img_html}'
            f'<b style="font-size:13px">{title}</b><br>'
            f'<span style="color:#666;font-size:12px">{_site_display_name(im["source_site"])} · {tipo_label}</span><br>'
            f'<span style="font-size:14px;font-weight:bold">{price_str}</span><br>'
            f'<a href="{im["source_url"]}" target="_blank" '
            f'style="font-size:12px;color:#3b82f6">Ver anúncio ↗</a>'
        )
        folium.Marker(
            location=[im["lat"], im["lng"]],
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=f'{tipo_label} — {price_str}',
            icon=folium.Icon(color=color),
        ).add_to(m)

    # Legend
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:10px 14px;border-radius:8px;
                border:1px solid #ddd;font-size:13px;
                box-shadow:2px 2px 8px rgba(0,0,0,0.15);">
      <b style="display:block;margin-bottom:6px">Legenda</b>
      <span style="color:#3b82f6;font-size:16px">●</span>&nbsp;Aluguel<br>
      <span style="color:#ef4444;font-size:16px">●</span>&nbsp;Compra
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    return templates.TemplateResponse(request, "mapa.html", {
        "active_tab": "mapa",
        "username": request.session.get("username"),
        "map_html": m._repr_html_(),
    })


@router.get("/historico", response_class=HTMLResponse)
async def historico(request: Request):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    import json
    conn = get_connection()
    runs_raw = get_runs(conn)
    conn.close()
    runs = []
    for r in runs_raw:
        d = dict(r)
        sites = json.loads(d.get("sites_scraped") or "[]")
        d["sites_count"] = len(sites)
        runs.append(d)
    return templates.TemplateResponse(request, "historico.html", {
        "active_tab": "historico",
        "username": request.session.get("username"),
        "runs": runs,
    })


@router.get("/partials/imoveis", response_class=HTMLResponse)
async def partial_imoveis(
    request: Request,
    tipo: str = "aluguel",
    site: str = "",
    status: str = "",
    neighborhood: str = "",
    category: str = "",
    sort: str = "first_seen",
    sort_dir: str = "desc",
    include_inactive: str = "",
    change_since: str = "",
):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    show_inactive = include_inactive in ("1", "true", "on")
    conn = get_connection()
    imoveis = get_imoveis(conn, tipo, site, status, neighborhood, category,
                          sort, sort_dir, include_inactive=show_inactive,
                          change_since=change_since)
    conn.close()
    return templates.TemplateResponse(request, "partials/_imovel_tabela.html", {
        "imoveis": imoveis,
        "tipo": tipo,
        "statuses": STATUSES,
        "sort": sort,
        "sort_dir": sort_dir,
        "filters": {
            "site": site, "status": status, "neighborhood": neighborhood,
            "category": category, "include_inactive": include_inactive,
            "change_since": change_since,
        },
    })


@router.get("/partials/imovel/{imovel_id}", response_class=HTMLResponse)
async def partial_imovel_detalhe(request: Request, imovel_id: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    imovel = get_imovel(conn, imovel_id)
    if not imovel:
        conn.close()
        return HTMLResponse("<p class='text-red-400 text-sm p-4'>Imóvel não encontrado.</p>", status_code=404)
    images = [r["url"] for r in get_imovel_images(conn, imovel_id)]
    price_history = get_imovel_price_history(conn, imovel_id)
    last_activity = get_last_activity(conn, imovel_id)
    conn.close()
    return templates.TemplateResponse(request, "partials/_imovel_detalhe.html", {
        "imovel": imovel,
        "images": images,
        "price_history": price_history,
        "last_activity": last_activity,
        "statuses": STATUSES,
    })


@router.post("/partials/imovel/{imovel_id}/status", response_class=HTMLResponse)
async def partial_update_status(request: Request, imovel_id: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    form = await request.form()
    new_status = str(form.get("status", ""))
    user_id = request.session["user_id"]
    conn = get_connection()
    old = get_imovel(conn, imovel_id)
    old_status = old["status"] if old else None
    tipo = old["transaction_type"] if old else "aluguel"
    update_imovel_status(conn, imovel_id, new_status)
    log_activity(conn, imovel_id, user_id, "status", old_status, new_status)
    mark_reviewed(conn, tipo)
    conn.commit()
    imovel = get_imovel(conn, imovel_id)
    conn.close()
    resp = templates.TemplateResponse(request, "partials/_imovel_linha.html", {
        "imovel": imovel,
        "statuses": STATUSES,
    })
    resp.headers["HX-Trigger-After-Settle"] = "imovelStatusChanged"
    return resp


@router.post("/partials/imovel/{imovel_id}/quick-status", response_class=HTMLResponse)
async def partial_quick_status(request: Request, imovel_id: str):
    """Quick-action status update: returns updated detail panel + OOB table row."""
    if not require_login(request):
        return HTMLResponse(status_code=401)
    form = await request.form()
    new_status = str(form.get("status", ""))
    user_id = request.session["user_id"]
    conn = get_connection()
    old = get_imovel(conn, imovel_id)
    old_status = old["status"] if old else None
    tipo = old["transaction_type"] if old else "aluguel"
    update_imovel_status(conn, imovel_id, new_status)
    log_activity(conn, imovel_id, user_id, "status", old_status, new_status)
    mark_reviewed(conn, tipo)
    conn.commit()
    imovel = get_imovel(conn, imovel_id)
    images = [r["url"] for r in get_imovel_images(conn, imovel_id)]
    price_history = get_imovel_price_history(conn, imovel_id)
    last_activity = get_last_activity(conn, imovel_id)
    conn.close()
    resp = templates.TemplateResponse(request, "partials/_imovel_detalhe.html", {
        "imovel": imovel,
        "images": images,
        "price_history": price_history,
        "last_activity": last_activity,
        "statuses": STATUSES,
    })
    resp.headers["HX-Trigger-After-Settle"] = "imovelStatusChanged"
    return resp


@router.get("/partials/imovel/{imovel_id}/edit", response_class=HTMLResponse)
async def partial_edit_get(request: Request, imovel_id: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    imovel = get_imovel(conn, imovel_id)
    conn.close()
    return templates.TemplateResponse(request, "partials/_imovel_modal_editar.html", {
        "imovel": imovel,
        "statuses": STATUSES,
    })


@router.post("/partials/imovel/{imovel_id}/edit", response_class=HTMLResponse)
async def partial_edit_post(request: Request, imovel_id: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    form = await request.form()
    address = str(form.get("address", "")).strip()
    comments = str(form.get("comments", "")).strip()
    gmaps_url = str(form.get("gmaps_url", "")).strip()

    lat, lng = None, None

    # Try Google Maps URL first (most precise)
    if gmaps_url:
        m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", gmaps_url)
        if m:
            lat, lng = float(m.group(1)), float(m.group(2))

    # Fall back to Nominatim geocoding
    if lat is None and address:
        try:
            gc = Nominatim(user_agent="imoveis-di/1.0", timeout=5)
            query = f"{address}, Dois Irmãos, RS, Brasil"
            location = gc.geocode(query)
            if location:
                lat, lng = location.latitude, location.longitude
        except (GeocoderTimedOut, GeocoderUnavailable):
            pass

    conn = get_connection()
    user_id = request.session["user_id"]
    old = get_imovel(conn, imovel_id)
    if old and old["address"] != address:
        log_activity(conn, imovel_id, user_id, "address", old["address"], address)
    if old and old["comments"] != comments:
        log_activity(conn, imovel_id, user_id, "comments", old["comments"], comments)
    update_imovel_fields(conn, imovel_id, address, comments, lat, lng)
    conn.commit()
    imovel = get_imovel(conn, imovel_id)
    images = [r["url"] for r in get_imovel_images(conn, imovel_id)]
    price_history = get_imovel_price_history(conn, imovel_id)
    last_activity_row = get_last_activity(conn, imovel_id)
    conn.close()
    return templates.TemplateResponse(request, "partials/_imovel_detalhe.html", {
        "imovel": imovel,
        "images": images,
        "price_history": price_history,
        "last_activity": last_activity_row,
        "statuses": STATUSES,
    })


@router.get("/partials/run/{run_id}", response_class=HTMLResponse)
async def partial_run_log(request: Request, run_id: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    run = get_run(conn, run_id)
    conn.close()
    log_text = run["log"] if run else "Log não encontrado."
    return HTMLResponse(content=f"<pre class='whitespace-pre-wrap'>{log_text}</pre>")
