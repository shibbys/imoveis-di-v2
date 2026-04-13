from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from storage.database import get_connection, mark_reviewed, update_schedule, get_workspace
from routers.auth import require_login

router = APIRouter()
templates = Jinja2Templates(directory="templates")


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
    conn.close()
    return templates.TemplateResponse("configuracoes.html", {
        "request": request,
        "active_tab": "configuracoes",
        "username": request.session.get("username"),
        "workspace": ws,
    })


@router.post("/configuracoes")
async def configuracoes_post(request: Request, schedule: str = Form(...)):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    conn = get_connection()
    update_schedule(conn, schedule)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/configuracoes", status_code=303)
