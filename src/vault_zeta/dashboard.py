"""Owner-only, read-only browser views for the Vault Zeta store."""

from __future__ import annotations

import argparse
import base64
import hmac
import json
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from urllib.parse import urlencode

from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .models import MemoryRecord
from .store import VaultZetaStore

BASE = "/dashboard"
PAGE_LIMIT = 50
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; style-src 'self'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


class OwnerAccess:
    def __init__(self, app: ASGIApp, *, credential: bytes) -> None:
        self.app = app
        self.credential = credential

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        authorization = Headers(scope=scope).getlist("authorization")
        if len(authorization) == 1:
            scheme, _, value = authorization[0].partition(" ")
            if scheme.lower() == "basic" and hmac.compare_digest(value.encode("latin-1"), self.credential):
                await self.app(scope, receive, send)
                return
        response = PlainTextResponse(
            "Owner sign-in required",
            status_code=401,
            headers={**SECURITY_HEADERS, "WWW-Authenticate": 'Basic realm="Vault Zeta", charset="UTF-8"'},
        )
        await response(scope, receive, send)


def link(route: str, **params: str) -> str:
    path = f"{BASE}/{route}"
    return escape(f"{path}?{urlencode(params)}" if params else path, quote=True)


def layout(title: str, active: str, content: str, *, status: int = 200) -> HTMLResponse:
    current_page = ' aria-current="page"'
    navigation = "".join(
        f'<a href="{link(route)}"{current_page if route == active else ""}>{label}</a>'
        for route, label in (("", "Overview"), ("memories", "Memories"), ("missions", "Missions"))
    )
    return HTMLResponse(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escape(title)} · Vault Zeta</title><link rel="stylesheet" href="{link("dashboard.css")}">'
        f'</head><body><a class="skip" href="#content">Skip to content</a><header class="top">'
        f'<div class="shell top-inner"><a class="brand" href="{link("")}"><span aria-hidden="true">Z</span>'
        f'Vault Zeta</a><nav aria-label="Vault navigation">{navigation}</nav><span class="badge">Read-only</span>'
        f'</div></header><main id="content" class="shell content" tabindex="-1">{content}</main></body></html>',
        status_code=status,
        headers=SECURITY_HEADERS,
    )


def mission_rows(store: VaultZetaStore, *, query: str = "", limit: int = PAGE_LIMIT):
    with store._lock:
        return store.db.execute(
            """
            WITH activity AS (
                SELECT mission_id, updated_at AS at FROM mission_snapshots
                UNION ALL SELECT mission_id, updated_at FROM mission_tasks
                UNION ALL SELECT mission_id, created_at FROM mission_events
            ), latest AS (
                SELECT mission_id, MAX(at) AS last_activity FROM activity GROUP BY mission_id
            )
            SELECT latest.*, snapshot.status, snapshot.revision
            FROM latest LEFT JOIN mission_snapshots snapshot USING (mission_id)
            WHERE instr(lower(latest.mission_id), lower(?)) > 0
            ORDER BY last_activity DESC, mission_id
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()


def missions_list(rows, *, query: str = "") -> str:
    if not rows:
        if query:
            return '<p class="empty">No missions match this search.</p>'
        return '<p class="empty">Missions appear here when agents save snapshots, tasks, or events.</p>'
    return '<ul class="records">' + "".join(
        f'<li><a href="{link("mission", id=row["mission_id"])}">{escape(row["mission_id"])}</a>'
        f'<span>{escape(row["status"] or "Activity only")} · {escape(row["last_activity"])}</span></li>'
        for row in rows
    ) + "</ul>"


def memories_list(memories: list[MemoryRecord], empty: str) -> str:
    if not memories:
        return f'<p class="empty">{escape(empty)}</p>'
    return '<ul class="records">' + "".join(
        f'<li><a href="{link("memory", id=memory.id)}">{escape(memory.content[:140])}'
        f'{"…" if len(memory.content) > 140 else ""}</a>'
        f'<span>{escape(memory.kind)} · {escape(memory.scope)}'
        f'{" · Superseded" if memory.superseded_by else " · Stale" if memory.stale else ""}</span></li>'
        for memory in memories
    ) + "</ul>"


def overview(request: Request) -> HTMLResponse:
    store = request.app.state.store
    with store._lock:
        metrics = store.db.execute(
            """SELECT (SELECT count(*) FROM memories), (SELECT count(*) FROM mission_snapshots),
                      (SELECT count(*) FROM mission_tasks), (SELECT count(*) FROM mission_events)"""
        ).fetchone()
    counts = "".join(
        f'<div><dt>{label}</dt><dd>{value:,}</dd></div>'
        for label, value in zip(("Memories", "Snapshots", "Tasks", "Events"), metrics, strict=True)
    )
    return layout("Overview", "", (
        '<h1>Vault overview</h1>'
        '<p class="lead">Review what agents have saved and where their work can resume.</p>'
        f'<dl class="metrics">{counts}</dl><div class="panels">'
        f'<section class="panel"><h2>Memories</h2>{memories_list(store.search("", limit=5), "No memories saved yet.")}'
        f'<a class="panel-link" href="{link("memories")}">Browse memories →</a></section>'
        f'<section class="panel"><h2>Mission activity</h2>{missions_list(mission_rows(store, limit=5))}'
        f'<a class="panel-link" href="{link("missions")}">Browse missions →</a></section></div>'
    ))


def memories(request: Request) -> HTMLResponse:
    q = request.query_params.get("q", "").strip()[:200]
    scope = request.query_params.get("scope", "").strip()[:200]
    history = request.query_params.get("history") == "1"
    records = request.app.state.store.search(
        q, scope=scope or None, limit=PAGE_LIMIT, include_stale=history, include_superseded=history,
    )
    return layout("Memories", "memories", (
        '<h1>Memories</h1><p class="lead">Search stored knowledge and follow its corrections.</p>'
        f'<form class="filters" action="{link("memories")}" method="get">'
        f'<label>Search memories<input name="q" type="search" value="{escape(q, quote=True)}" maxlength="200"></label>'
        f'<label>Scope<input name="scope" value="{escape(scope, quote=True)}" maxlength="200"></label>'
        f'<label class="check"><input type="checkbox" name="history" value="1"{" checked" if history else ""}>'
        'Include stale and superseded</label><button>Search</button></form>'
        f'<section class="panel"><h2>Results</h2>{memories_list(records, "No memories match this view.")}</section>'
    ))


def memory_detail(request: Request) -> HTMLResponse:
    store = request.app.state.store
    try:
        record = store.get_memory(request.query_params.get("id", ""))
        lineage = store.get_lineage(record.id)
    except KeyError as exc:
        raise HTTPException(404, "Memory not found") from exc
    facts = (
        ("Scope", record.scope), ("Kind", record.kind), ("Confidence", f"{record.confidence:.0%}"),
        ("Source", record.source or "None recorded"), ("Updated", record.updated_at),
    )
    details = "".join(f"<div><dt>{label}</dt><dd>{escape(value)}</dd></div>" for label, value in facts)
    return layout("Memory detail", "memories", (
        f'<a class="back" href="{link("memories")}">← Memories</a><h1>Memory detail</h1>'
        f'<section class="panel"><p class="memory-body">{escape(record.content)}</p><dl class="facts">{details}</dl>'
        f'</section><section class="panel"><h2>Correction history</h2>{memories_list(lineage, "")}</section>'
    ))


def missions(request: Request) -> HTMLResponse:
    q = request.query_params.get("q", "").strip()[:200]
    records = mission_rows(request.app.state.store, query=q)
    return layout("Missions", "missions", (
        '<h1>Missions</h1><p class="lead">See which work is ready to resume and what changed.</p>'
        f'<form class="filters mission-filters" method="get" action="{link("missions")}">'
        f'<label>Search missions<input type="search" name="q" value="{escape(q, quote=True)}" maxlength="200"></label>'
        '<button>Search</button></form>'
        f'<section class="panel">{missions_list(records, query=q)}</section>'
    ))


def mission_detail(request: Request) -> HTMLResponse:
    store = request.app.state.store
    mission_id = request.query_params.get("id", "")
    snapshot = store.load_mission(mission_id)
    tasks = store.list_tasks(mission_id)
    with store._lock:
        events = store.db.execute(
            "SELECT seq, event_type, payload_json, created_at FROM mission_events "
            "WHERE mission_id = ? ORDER BY seq DESC LIMIT ?", (mission_id, PAGE_LIMIT),
        ).fetchall()
    if not snapshot and not tasks and not events:
        raise HTTPException(404, "Mission not found")
    state = '<p class="empty">No snapshot saved for this mission.</p>'
    if snapshot:
        state = (
            f'<p class="summary">{escape(snapshot.status)} · Revision {snapshot.revision}</p>'
            f'<pre>{escape(json.dumps(snapshot.snapshot, ensure_ascii=False, indent=2))}</pre>'
        )
    task_order = {"pending": 0, "running": 1, "blocked": 2, "failed": 3, "completed": 4, "skipped": 5}
    tasks.sort(key=lambda task: task_order[task.status])
    task_items = "".join(
        f'<li><strong>{escape(task.title)}</strong><span>{escape("Ready" if task.status == "pending" else task.status)}'
        f'{" · Depends on " + escape(", ".join(task.dependencies)) if task.dependencies else ""}</span></li>'
        for task in tasks
    )
    timeline = "".join(
        f'<li><details><summary>{escape(event["event_type"].replace("_", " "))}'
        f'<span>#{event["seq"]} · {escape(event["created_at"])}</span></summary>'
        f'<pre>{escape(event["payload_json"])}</pre></details></li>'
        for event in events
    )
    task_summary = f'<ul class="records">{task_items}</ul>' if tasks else '<p class="empty">No tasks recorded.</p>'
    history = f'<ol class="records">{timeline}</ol>' if events else '<p class="empty">No events recorded.</p>'
    return layout("Mission detail", "missions", (
        f'<a class="back" href="{link("missions")}">← Missions</a><h1>{escape(mission_id)}</h1>'
        f'<div class="panels"><section class="panel"><h2>Current snapshot</h2>{state}</section>'
        f'<section class="panel"><h2>Tasks</h2>{task_summary}</section></div>'
        f'<section class="panel"><h2>Recent events</h2>{history}</section>'
    ))


def create_dashboard(path: str | Path, *, username: str, password: str) -> Starlette:
    if not username or ":" in username or len(password) < 24:
        raise ValueError("Configure an owner username and a dashboard password of at least 24 characters")

    @asynccontextmanager
    async def lifespan(app: Starlette):
        with VaultZetaStore(path, read_only=True) as store:
            app.state.store = store
            yield

    async def error(request: Request, exc: HTTPException) -> HTMLResponse:
        return layout("Unavailable", "", f'<h1>{escape(str(exc.detail))}</h1>', status=exc.status_code)

    async def redirect(request: Request) -> RedirectResponse:
        return RedirectResponse(link(""), headers=SECURITY_HEADERS)

    def stylesheet(request: Request) -> Response:
        return Response(Path(__file__).with_name("dashboard.css").read_bytes(),
                        media_type="text/css", headers=SECURITY_HEADERS)

    app = Starlette(
        routes=[
            Route(BASE, redirect), Route(link(""), overview), Route(link("memories"), memories),
            Route(link("memory"), memory_detail), Route(link("missions"), missions),
            Route(link("mission"), mission_detail), Route(link("dashboard.css"), stylesheet),
        ],
        lifespan=lifespan,
        exception_handlers={HTTPException: error},
    )
    app.add_middleware(OwnerAccess, credential=base64.b64encode(f"{username}:{password}".encode()))
    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=14873)
    args = parser.parse_args()
    app = create_dashboard(args.db, username=args.username, password=args.password_file.read_text().strip())
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
