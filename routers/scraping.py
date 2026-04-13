from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from routers.auth import require_login

router = APIRouter()


@router.post("/scraping/trigger", response_class=HTMLResponse)
async def trigger_scraping(request: Request):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    return HTMLResponse(
        content='<p class="text-yellow-400 text-xs">Scraping será configurado na Task 8.</p>'
    )


@router.get("/scraping/stream")
async def scraping_stream(request: Request):
    return HTMLResponse(content="", status_code=200)
