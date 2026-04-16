import re
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")


def _site_display_name(name: str) -> str:
    name = re.sub(r"_(compra|aluguel)$", "", name)
    return name.replace("_", " ").title()


def _format_duration(seconds) -> str:
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return "—"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


templates.env.filters["site_name"] = _site_display_name
templates.env.filters["format_duration"] = _format_duration
