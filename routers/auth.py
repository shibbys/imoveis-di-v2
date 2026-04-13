import bcrypt
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from storage.database import get_connection, get_user_by_username

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def get_current_user_id(request: Request) -> int | None:
    """Returns user_id from session, or None if not authenticated."""
    return request.session.get("user_id")


def require_login(request: Request) -> int | None:
    """Returns user_id if logged in, else None. Use to guard routes."""
    return request.session.get("user_id")


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if require_login(request):
        return RedirectResponse(url="/aluguel", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    conn = get_connection()
    user = get_user_by_username(conn, username)
    conn.close()
    authenticated = False
    if user:
        try:
            authenticated = bcrypt.checkpw(password.encode(), user["password_hash"].encode())
        except (ValueError, Exception):
            authenticated = False

    if authenticated:
        request.session["user_id"] = user["id"]
        request.session["username"] = user["username"]
        return RedirectResponse(url="/aluguel", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Usuário ou senha incorretos"},
        status_code=200
    )


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
