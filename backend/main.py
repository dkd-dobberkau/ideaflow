from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, Response
from sse_starlette.sse import EventSourceResponse
from contextlib import asynccontextmanager
import asyncio
import json
import numpy as np
from sklearn.cluster import KMeans
from datetime import datetime

from models import NostrEvent
from qdrant_service import (
    init_collection, store_idea, search_similar,
    find_related, get_all_vectors_with_payload, get_idea_by_event_id,
    find_referencing_ideas
)
from nostr_client import NostrClient

event_queues: list[asyncio.Queue] = []
nostr_client: NostrClient = None


async def handle_new_idea(event: dict):
    references = [tag[1] for tag in event.get("tags", []) if tag[0] == "e"]

    store_idea(
        event_id=event["id"],
        content=event["content"],
        pubkey=event["pubkey"],
        created_at=event["created_at"],
        references=references
    )

    for queue in event_queues:
        await queue.put(event)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global nostr_client

    init_collection()
    nostr_client = NostrClient()

    async def start_nostr():
        try:
            await nostr_client.connect()
            await nostr_client.subscribe(
                "ideas",
                [{"kinds": [30023], "#t": ["idea"]}],
                handle_new_idea
            )
            print("Nostr client connected and subscribed")
        except Exception as e:
            print(f"Nostr connection failed: {e}")

    asyncio.create_task(start_nostr())

    yield

    if nostr_client:
        await nostr_client.close()


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("frontend/index.html")


@app.get("/components/idea-card/{event_id}", response_class=HTMLResponse)
async def idea_card(event_id: str):
    idea = get_idea_by_event_id(event_id)
    if not idea:
        raise HTTPException(404, "Idea not found")

    return render_idea_card_from_payload(idea)


@app.post("/api/ideas")
async def create_idea(event: NostrEvent):
    event_dict = event.model_dump()
    references = [tag[1] for tag in event.tags if tag[0] == "e"]

    # Try to publish to Nostr relay (non-blocking if it fails)
    if nostr_client:
        try:
            await nostr_client.publish_event(event_dict, timeout=3.0)
        except Exception as e:
            print(f"Nostr publish failed (storing locally): {e}")

    # Always store in Qdrant as local cache
    store_idea(
        event_id=event.id,
        content=event.content,
        pubkey=event.pubkey,
        created_at=event.created_at,
        references=references
    )

    # Broadcast to SSE clients
    for queue in event_queues:
        await queue.put(event_dict)

    return {"status": "ok", "event_id": event.id}


@app.get("/api/search")
async def search_ideas(q: str, limit: int = 10, pubkey: str = None, time: str = None):
    results = search_similar(q, limit=limit, pubkey_filter=pubkey, time_range=time)
    return {"results": results}


@app.get("/api/related/{event_id}")
async def get_related(event_id: str, limit: int = 5):
    results = find_related(event_id, limit=limit)
    return {"results": results}


@app.get("/api/clusters")
async def get_clusters():
    points = get_all_vectors_with_payload(limit=1000)

    if len(points) < 5:
        return {"clusters": []}

    vectors = np.array([p.vector for p in points])
    n_clusters = min(5, len(points) // 3)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(vectors)

    clusters = {}
    for i, point in enumerate(points):
        cluster_id = int(labels[i])
        if cluster_id not in clusters:
            clusters[cluster_id] = []
        clusters[cluster_id].append({
            "event_id": point.id,
            "content_preview": point.payload.get("content_preview", "")
        })

    return {"clusters": list(clusters.values())}


@app.get("/api/export")
async def export_ideas(format: str = "json", pubkey: str = None, time: str = None):
    points = get_all_vectors_with_payload(limit=1000, time_range=time)

    if pubkey:
        points = [p for p in points if p.payload.get("pubkey") == pubkey]

    sorted_points = sorted(
        points,
        key=lambda p: p.payload.get("created_at", 0),
        reverse=True
    )

    ideas = []
    for point in sorted_points:
        ideas.append({
            "event_id": point.payload.get("nostr_event_id", str(point.id)),
            "content": point.payload.get("content_preview", ""),
            "pubkey": point.payload.get("pubkey", ""),
            "created_at": point.payload.get("created_at", 0),
            "references": point.payload.get("references", [])
        })

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if format == "markdown":
        lines = ["# IdeaFlow Export", f"\nExportiert: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"]
        for idea in ideas:
            created = datetime.fromtimestamp(idea["created_at"]).strftime("%d.%m.%Y %H:%M")
            lines.append(f"## {created}")
            lines.append(f"\n{idea['content']}\n")
            lines.append(f"*Pubkey: {idea['pubkey'][:16]}...*\n")
            if idea["references"]:
                lines.append(f"*Referenzen: {', '.join(idea['references'][:3])}*\n")
            lines.append("---\n")

        content = "\n".join(lines)
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=ideaflow_export_{timestamp}.md"}
        )
    else:
        content = json.dumps({"ideas": ideas, "exported_at": timestamp}, indent=2, ensure_ascii=False)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=ideaflow_export_{timestamp}.json"}
        )


@app.get("/api/ideas/{event_id}/references")
async def get_idea_references(event_id: str):
    idea = get_idea_by_event_id(event_id)
    if not idea:
        raise HTTPException(404, "Idea not found")

    referenced_ids = idea.get("references", [])
    referenced = []
    for ref_id in referenced_ids:
        ref_idea = get_idea_by_event_id(ref_id)
        if ref_idea:
            referenced.append(ref_idea)

    referencing = find_referencing_ideas(event_id)

    return {
        "referenced": referenced,
        "referencing": referencing
    }


@app.get("/api/network-data")
async def get_network_data():
    points = get_all_vectors_with_payload(limit=500)

    nodes = []
    links = []

    for point in points:
        nodes.append({
            "id": point.id,
            "content_preview": point.payload.get("content_preview", ""),
            "pubkey": point.payload.get("pubkey", "")
        })

        for ref in point.payload.get("references", []):
            links.append({
                "source": point.id,
                "target": ref
            })

    return {"nodes": nodes, "links": links}


@app.get("/stream")
async def stream(request: Request):
    queue = asyncio.Queue()
    event_queues.append(queue)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {
                        "event": "new-idea",
                        "data": json.dumps(event)
                    }
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            event_queues.remove(queue)

    return EventSourceResponse(event_generator())


@app.get("/partials/search-results", response_class=HTMLResponse)
async def search_results_partial(q: str, time: str = None):
    if not q.strip():
        return "<div class='text-gray-500'>Suchbegriff eingeben...</div>"

    results = search_similar(q, limit=10, time_range=time)

    html_parts = []
    for r in results:
        score_percent = int(r["score"] * 100)
        html_parts.append(f'''
        <article class="idea-card"
                 hx-get="/components/idea-card/{r['event_id']}"
                 hx-trigger="click"
                 hx-target="#idea-detail"
                 hx-swap="innerHTML">
            <p class="content">{r['content_preview']}</p>
            <div class="meta">
                <span class="score">{score_percent}% Relevanz</span>
                <span class="pubkey">{r['pubkey'][:8]}...</span>
            </div>
        </article>
        ''')

    if not html_parts:
        return "<div class='text-gray-500'>Keine Ergebnisse gefunden</div>"

    return "\n".join(html_parts)


@app.get("/partials/recent-ideas", response_class=HTMLResponse)
async def recent_ideas_partial(time: str = None):
    points = get_all_vectors_with_payload(limit=20, time_range=time)

    sorted_points = sorted(
        points,
        key=lambda p: p.payload.get("created_at", 0),
        reverse=True
    )

    html_parts = []
    for point in sorted_points[:10]:
        event_id = point.payload.get("nostr_event_id", str(point.id))
        html_parts.append(f'''
        <article class="idea-card"
                 hx-get="/components/idea-card/{event_id}"
                 hx-trigger="click"
                 hx-target="#idea-detail"
                 hx-swap="innerHTML">
            <p class="content">{point.payload.get("content_preview", "")}</p>
            <div class="meta">
                <span class="pubkey">{point.payload.get("pubkey", "")[:8]}...</span>
            </div>
        </article>
        ''')

    if not html_parts:
        return "<div class='text-gray-500'>Noch keine Ideen vorhanden</div>"

    return "\n".join(html_parts)


def render_idea_card(event: dict, related: list) -> str:
    related_html = ""
    if related:
        related_items = [
            f'<li><a href="#" hx-get="/components/idea-card/{r["event_id"]}" '
            f'hx-target="#idea-detail">{r["content_preview"][:50]}...</a></li>'
            for r in related
        ]
        related_html = f'''
        <div class="related">
            <h4>Ähnliche Ideen</h4>
            <ul>{"".join(related_items)}</ul>
        </div>
        '''

    from datetime import datetime
    created = datetime.fromtimestamp(event["created_at"]).strftime("%d.%m.%Y %H:%M")

    return f'''
    <article class="idea-detail">
        <p class="content">{event["content"]}</p>
        <div class="meta">
            <time>{created}</time>
            <span class="pubkey">{event["pubkey"][:16]}...</span>
        </div>
        {related_html}
    </article>
    '''


def render_idea_card_from_payload(payload: dict) -> str:
    created = datetime.fromtimestamp(payload.get("created_at", 0)).strftime("%d.%m.%Y %H:%M")
    event_id = payload.get("event_id") or payload.get("nostr_event_id", "")

    # Get referenced ideas (what this idea links to)
    referenced_ids = payload.get("references", [])
    referenced_html = ""
    if referenced_ids:
        referenced_items = []
        for ref_id in referenced_ids[:5]:
            ref_idea = get_idea_by_event_id(ref_id)
            if ref_idea:
                referenced_items.append(
                    f'<li><a href="#" hx-get="/components/idea-card/{ref_id}" '
                    f'hx-target="#idea-detail">{ref_idea.get("content_preview", "")[:50]}...</a></li>'
                )
        if referenced_items:
            referenced_html = f'''
            <div class="references">
                <h4>Verweist auf</h4>
                <ul>{"".join(referenced_items)}</ul>
            </div>
            '''

    # Get referencing ideas (what links to this idea)
    referencing = find_referencing_ideas(event_id) if event_id else []
    referencing_html = ""
    if referencing:
        referencing_items = [
            f'<li><a href="#" hx-get="/components/idea-card/{r["event_id"]}" '
            f'hx-target="#idea-detail">{r.get("content_preview", "")[:50]}...</a></li>'
            for r in referencing[:5]
        ]
        referencing_html = f'''
        <div class="references">
            <h4>Verwiesen von</h4>
            <ul>{"".join(referencing_items)}</ul>
        </div>
        '''

    # Similar ideas
    related = find_related(event_id, limit=3) if event_id else []
    related_html = ""
    if related:
        related_items = [
            f'<li><a href="#" hx-get="/components/idea-card/{r["event_id"]}" '
            f'hx-target="#idea-detail">{r["content_preview"][:50]}...</a></li>'
            for r in related
        ]
        related_html = f'''
        <div class="related">
            <h4>Ähnliche Ideen</h4>
            <ul>{"".join(related_items)}</ul>
        </div>
        '''

    return f'''
    <article class="idea-detail">
        <p class="content">{payload.get("content_preview", "")}</p>
        <div class="meta">
            <time>{created}</time>
            <span class="pubkey">{payload.get("pubkey", "")[:16]}...</span>
        </div>
        {referenced_html}
        {referencing_html}
        {related_html}
    </article>
    '''
