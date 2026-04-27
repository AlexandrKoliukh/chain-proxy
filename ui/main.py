"""FastAPI entrypoint — basic-auth web UI for chain-proxy."""
from __future__ import annotations

import asyncio
import os
import re
from typing import Annotated, Literal

import uvicorn
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth, config as cfg_mod, deploy, keys as keys_mod, status as status_mod, tls, vless
from .paths import INITIAL_PASSWORD_FILE, STATIC, TEMPLATES, ensure_data_dirs

app = FastAPI(title="chain-proxy UI")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES))

_CLIENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")


def _user(creds: Annotated[HTTPBasicCredentials, Depends(auth.basic)], request: Request) -> str:
    return auth.require(request, creds)


User = Annotated[str, Depends(_user)]


def _has_initial_password() -> bool:
    return INITIAL_PASSWORD_FILE.exists()


def _ctx(request: Request, **extra) -> dict:
    cfg = cfg_mod.load()
    base = {
        "request": request,
        "cfg": cfg,
        "has_initial": _has_initial_password(),
        "job_status": deploy.jobs.status(),
    }
    base.update(extra)
    return base


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User):
    return RedirectResponse(url="/settings", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
async def settings_get(request: Request, user: User):
    return templates.TemplateResponse("settings.html", _ctx(request))


@app.post("/settings", response_class=HTMLResponse)
async def settings_post(
    request: Request,
    user: User,
    vps1_ip: Annotated[str, Form()] = "",
    vps2_ip: Annotated[str, Form()] = "",
    vps2_user: Annotated[str, Form()] = "root",
    vps2_password: Annotated[str, Form()] = "",
    vps2_port: Annotated[int, Form()] = 22,
    reality_dest_host: Annotated[str, Form()] = "www.microsoft.com",
    reality_fingerprint: Annotated[str, Form()] = "chrome",
):
    cfg = cfg_mod.load()
    cfg.hosts.vps1_ip = vps1_ip.strip()
    cfg.hosts.vps2_ip = vps2_ip.strip()
    cfg.hosts.vps2_user = vps2_user.strip() or "root"
    if vps2_password:
        cfg.hosts.vps2_password = vps2_password
    cfg.hosts.vps2_port = vps2_port
    cfg.reality.dest_host = reality_dest_host.strip() or "www.microsoft.com"
    cfg.reality.fingerprint = reality_fingerprint.strip() or "chrome"
    cfg_mod.save(cfg)
    return templates.TemplateResponse(
        "settings.html", _ctx(request, message="Сохранено.")
    )


@app.post("/settings/password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    user: User,
    new_password: Annotated[str, Form()],
):
    if len(new_password) < 8:
        return templates.TemplateResponse(
            "settings.html",
            _ctx(request, error="Пароль должен быть не меньше 8 символов."),
            status_code=400,
        )
    auth.change_password(new_password)
    return templates.TemplateResponse(
        "settings.html",
        _ctx(request, message="Пароль обновлён. Initial-password удалён."),
    )


@app.post("/api/gen-keys", response_class=HTMLResponse)
async def gen_keys(request: Request, user: User):
    cfg = cfg_mod.load()
    rc, out, cfg = await keys_mod.regenerate(cfg)
    if rc != 0:
        return templates.TemplateResponse(
            "settings.html",
            _ctx(request, error=f"gen-keys failed (exit {rc}). См. логи:\n{out}"),
            status_code=500,
        )
    return templates.TemplateResponse(
        "settings.html",
        _ctx(request, message="Ключи сгенерированы и сохранены."),
    )


@app.get("/deploy", response_class=HTMLResponse)
async def deploy_get(request: Request, user: User):
    return templates.TemplateResponse("deploy.html", _ctx(request))


@app.post("/api/deploy", response_class=HTMLResponse)
async def deploy_start(
    request: Request,
    user: User,
    limit: Annotated[Literal["all", "entry", "exit"], Form()] = "all",
):
    cfg = cfg_mod.load()
    if deploy.jobs.current is not None:
        raise HTTPException(409, "another job is running")
    asyncio.create_task(deploy.start_deploy(cfg, limit, local_entry=True))
    return RedirectResponse(url="/deploy", status_code=303)


@app.get("/api/deploy/stream")
async def deploy_stream(user: User):
    job = deploy.jobs.current or deploy.jobs.last
    if job is None:
        async def empty():
            yield "data: (no job yet)\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")

    async def event_gen():
        async for line in job.follow():
            for sub in line.splitlines() or [""]:
                yield f"data: {sub}\n\n"
        yield f"event: done\ndata: {job.exit_code}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/status", response_class=HTMLResponse)
async def status_page(request: Request, user: User):
    cfg = cfg_mod.load()
    data = await status_mod.collect(cfg)
    return templates.TemplateResponse(
        "status.html", _ctx(request, status=data)
    )


@app.get("/client", response_class=HTMLResponse)
async def client_redirect(request: Request, user: User):
    return RedirectResponse(url="/clients", status_code=301)


@app.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request, user: User):
    cfg = cfg_mod.load()
    clients = vless.build(cfg)
    msg = None
    if request.query_params.get("added"):
        msg = "Клиент добавлен. Нужен Deploy для применения изменений."
    elif request.query_params.get("deleted"):
        msg = "Клиент удалён. Нужен Deploy для применения изменений."
    return templates.TemplateResponse(
        "client.html",
        _ctx(request, clients=clients, missing=vless.missing_reasons(cfg), message=msg),
    )


@app.post("/clients", response_class=HTMLResponse)
async def add_client(request: Request, user: User, name: Annotated[str, Form()]):
    name = name.strip()
    cfg = cfg_mod.load()
    if not _CLIENT_NAME_RE.match(name):
        return templates.TemplateResponse(
            "client.html",
            _ctx(request, clients=vless.build(cfg), missing=vless.missing_reasons(cfg),
                 error="Имя клиента: только буквы, цифры, - и _, до 32 символов."),
            status_code=400,
        )
    if any(c.name == name for c in cfg.clients):
        return templates.TemplateResponse(
            "client.html",
            _ctx(request, clients=vless.build(cfg), missing=vless.missing_reasons(cfg),
                 error=f"Клиент «{name}» уже существует."),
            status_code=400,
        )
    cfg = cfg_mod.new_client(name, cfg)
    cfg_mod.save(cfg)
    return RedirectResponse(url="/clients?added=1", status_code=303)


@app.post("/clients/{name}/delete", response_class=HTMLResponse)
async def delete_client(request: Request, user: User, name: str):
    cfg = cfg_mod.load()
    if len(cfg.clients) <= 1:
        return templates.TemplateResponse(
            "client.html",
            _ctx(request, clients=vless.build(cfg), missing=vless.missing_reasons(cfg),
                 error="Нельзя удалить последнего клиента."),
            status_code=400,
        )
    cfg = cfg_mod.remove_client(name, cfg)
    cfg_mod.save(cfg)
    return RedirectResponse(url="/clients?deleted=1", status_code=303)


@app.get("/clients/{name}/config")
async def download_client_config(name: str, user: User):
    cfg = cfg_mod.load()
    entry = next((c for c in cfg.clients if c.name == name), None)
    if entry is None:
        raise HTTPException(404, f"Client {name!r} not found")
    if not cfg.hosts.vps1_ip or not cfg.keys.entry_public_key or not cfg.keys.entry_short_id:
        raise HTTPException(400, "Config not ready: missing IP or keys")
    uri = vless._uri(entry.uuid, entry.name, cfg.hosts.vps1_ip, cfg)
    return PlainTextResponse(
        content=uri + "\n",
        headers={"Content-Disposition": f'attachment; filename="vless-{entry.name}.txt"'},
    )


def run() -> None:
    ensure_data_dirs()
    plain = auth.ensure_initial()
    if plain:
        print(f"[chain-proxy-ui] initial admin password: {plain}", flush=True)
    cn = os.environ.get("CHAIN_PROXY_CN") or cfg_mod.load().hosts.vps1_ip or "chain-proxy"
    cert, key = tls.ensure(cn)
    host = os.environ.get("CHAIN_PROXY_HOST", "0.0.0.0")
    port = int(os.environ.get("CHAIN_PROXY_PORT", "8443"))
    uvicorn.run(
        app,
        host=host,
        port=port,
        ssl_certfile=cert,
        ssl_keyfile=key,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    run()
