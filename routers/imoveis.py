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
        "filters": {},
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
    conn.close()
    m = folium.Map(location=[-29.6167, -51.0833], zoom_start=14)
    for im in list(imoveis_aluguel) + list(imoveis_compra):
        if im["lat"] and im["lng"]:
            color = STATUS_COLORS.get(im["status"], "blue")
            price_str = f'R$ {im["price"]:,.0f}'.replace(",", ".") if im["price"] else "—"
            popup_html = f'<b>{im["source_site"]}</b><br>{im["title"] or im["category"]}<br>{price_str}<br><a href="{im["source_url"]}" target="_blank">Ver anúncio ↗</a>'
            folium.Marker(
                location=[im["lat"], im["lng"]],
                popup=folium.Popup(popup_html, max_width=250),
                tooltip=f'{im["source_site"]} — {price_str}',
                icon=folium.Icon(color=color)
            ).add_to(m)
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
    price_min: float = 0,
    price_max: float = 0,
):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    imoveis = get_imoveis(conn, tipo, site, status, neighborhood, category, price_min, price_max)
    conn.close()
    return templates.TemplateResponse(request, "partials/_imovel_tabela.html", {
        "imoveis": imoveis,
        "tipo": tipo,
        "statuses": STATUSES,
        "filters": {
            "site": site, "status": status, "neighborhood": neighborhood,
            "category": category, "price_min": price_min, "price_max": price_max,
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
    return templates.TemplateResponse(request, "partials/_imovel_linha.html", {
        "imovel": imovel,
        "statuses": STATUSES,
    })


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
