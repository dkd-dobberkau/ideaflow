# IdeaFlow: Dezentrale Ideen-Webapp

## Projektübersicht

Eine moderne Ideen-Management-Webapp, die persönliche Souveränität mit emergentem Netzwerk-Denken verbindet.

**Kernprinzipien:**
- Dezentrale Identität via Nostr (kryptografische Schlüsselpaare)
- Semantische Suche via Qdrant Vektordatenbank
- Hypermedia-getriebenes Frontend mit HTMX
- Emergente Verbindungen zwischen Ideen und Menschen

## Technologie-Stack

| Komponente | Technologie | Zweck |
|------------|-------------|-------|
| Frontend | HTML + HTMX + Alpine.js | Hypermedia SPA ohne Build-Step |
| Backend | Python FastAPI | API + SSE + Nostr/Qdrant Bridge |
| Vektordatenbank | Qdrant | Semantische Ähnlichkeitssuche |
| Event-Store | nostr-rs-relay | Dezentrale Datenhaltung |
| Embeddings | sentence-transformers | Lokale Vektorisierung |
| Styling | Tailwind CSS (CDN) | Utility-first CSS |

## Verzeichnisstruktur

```
ideaflow/
├── backend/
│   ├── main.py              # FastAPI App
│   ├── nostr_client.py      # Nostr Relay Kommunikation
│   ├── qdrant_service.py    # Vektor-Operationen
│   ├── embedding_service.py # Text zu Vektor
│   ├── models.py            # Pydantic Models
│   └── requirements.txt
├── frontend/
│   ├── index.html           # Haupt-SPA
│   ├── components/          # HTMX Partials
│   │   ├── idea-card.html
│   │   ├── idea-form.html
│   │   ├── search-results.html
│   │   └── network-graph.html
│   └── static/
│       ├── app.js           # Alpine.js + nostr-tools
│       └── styles.css       # Custom Styles
├── docker-compose.yml
└── README.md
```

## Phase 1: Infrastruktur aufsetzen

### Docker Compose

Erstelle `docker-compose.yml`:

```yaml
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334

  nostr-relay:
    image: scsibug/nostr-rs-relay:latest
    ports:
      - "8080:8080"
    volumes:
      - nostr_data:/usr/src/app/db
      - ./config.toml:/usr/src/app/config.toml
    command: ["./nostr-rs-relay", "--config", "/usr/src/app/config.toml"]

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - NOSTR_RELAY_URL=ws://nostr-relay:8080
      - EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
    depends_on:
      - qdrant
      - nostr-relay
    volumes:
      - ./backend:/app
      - model_cache:/root/.cache

volumes:
  qdrant_data:
  nostr_data:
  model_cache:
```

### Nostr Relay Config

Erstelle `config.toml`:

```toml
[info]
relay_url = "ws://localhost:8080"
name = "IdeaFlow Relay"
description = "Private relay for idea management"

[database]
engine = "sqlite"
data_directory = "db"

[network]
port = 8080
address = "0.0.0.0"

[limits]
max_event_bytes = 131072
max_ws_message_bytes = 131072

[authorization]
# Später: Whitelist für bekannte Pubkeys
pubkey_whitelist = []
```

## Phase 2: Backend Implementation

### requirements.txt

```
fastapi==0.109.0
uvicorn[standard]==0.27.0
qdrant-client==1.7.0
sentence-transformers==2.2.2
websockets==12.0
pydantic==2.5.3
python-dotenv==1.0.0
secp256k1==0.14.0
sse-starlette==1.8.2
```

### models.py

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class IdeaCreate(BaseModel):
    content: str
    references: Optional[List[str]] = []  # Event IDs

class IdeaResponse(BaseModel):
    event_id: str
    pubkey: str
    content: str
    created_at: datetime
    references: List[str]
    similarity_score: Optional[float] = None

class SearchQuery(BaseModel):
    query: str
    limit: int = 10
    pubkey_filter: Optional[str] = None

class NostrEvent(BaseModel):
    id: str
    pubkey: str
    created_at: int
    kind: int
    tags: List[List[str]]
    content: str
    sig: str
```

### embedding_service.py

```python
from sentence_transformers import SentenceTransformer
from functools import lru_cache
import os

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

@lru_cache(maxsize=1)
def get_model():
    return SentenceTransformer(MODEL_NAME)

def create_embedding(text: str) -> list[float]:
    model = get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()

def create_embeddings_batch(texts: list[str]) -> list[list[float]]:
    model = get_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()
```

### qdrant_service.py

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue
)
import os
from typing import Optional
from .embedding_service import create_embedding

COLLECTION_NAME = "ideas"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2

client: Optional[QdrantClient] = None

def get_client() -> QdrantClient:
    global client
    if client is None:
        client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", 6333))
        )
    return client

def init_collection():
    client = get_client()
    collections = client.get_collections().collections
    exists = any(c.name == COLLECTION_NAME for c in collections)
    
    if not exists:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE
            )
        )
        # Payload indices für schnelles Filtern
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="pubkey",
            field_schema="keyword"
        )
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="created_at",
            field_schema="integer"
        )

def store_idea(event_id: str, content: str, pubkey: str, 
               created_at: int, references: list[str]):
    client = get_client()
    vector = create_embedding(content)
    
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=event_id,
                vector=vector,
                payload={
                    "nostr_event_id": event_id,
                    "pubkey": pubkey,
                    "created_at": created_at,
                    "references": references,
                    "content_preview": content[:200]
                }
            )
        ]
    )

def search_similar(query: str, limit: int = 10, 
                   pubkey_filter: Optional[str] = None) -> list[dict]:
    client = get_client()
    query_vector = create_embedding(query)
    
    search_filter = None
    if pubkey_filter:
        search_filter = Filter(
            must=[
                FieldCondition(
                    key="pubkey",
                    match=MatchValue(value=pubkey_filter)
                )
            ]
        )
    
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=limit,
        query_filter=search_filter,
        with_payload=True
    )
    
    return [
        {
            "event_id": hit.id,
            "score": hit.score,
            **hit.payload
        }
        for hit in results
    ]

def find_related(event_id: str, limit: int = 5) -> list[dict]:
    client = get_client()
    
    # Hole den Vektor der Ausgangsidee
    points = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[event_id],
        with_vectors=True
    )
    
    if not points:
        return []
    
    vector = points[0].vector
    
    # Suche ähnliche, schließe die Ausgangsidee aus
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=vector,
        limit=limit + 1,  # +1 weil wir die Quelle ausschließen
        with_payload=True
    )
    
    return [
        {
            "event_id": hit.id,
            "score": hit.score,
            **hit.payload
        }
        for hit in results
        if hit.id != event_id
    ][:limit]
```

### nostr_client.py

```python
import asyncio
import json
import websockets
from typing import Callable, Optional
import os

RELAY_URL = os.getenv("NOSTR_RELAY_URL", "ws://localhost:8080")

class NostrClient:
    def __init__(self, relay_url: str = RELAY_URL):
        self.relay_url = relay_url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.subscriptions: dict[str, Callable] = {}
    
    async def connect(self):
        self.ws = await websockets.connect(self.relay_url)
    
    async def close(self):
        if self.ws:
            await self.ws.close()
    
    async def publish_event(self, event: dict) -> bool:
        if not self.ws:
            await self.connect()
        
        message = json.dumps(["EVENT", event])
        await self.ws.send(message)
        
        # Warte auf OK Response
        response = await self.ws.recv()
        data = json.loads(response)
        
        if data[0] == "OK":
            return data[2]  # True wenn akzeptiert
        return False
    
    async def subscribe(self, sub_id: str, filters: list[dict], 
                       callback: Callable):
        if not self.ws:
            await self.connect()
        
        self.subscriptions[sub_id] = callback
        message = json.dumps(["REQ", sub_id, *filters])
        await self.ws.send(message)
    
    async def fetch_events(self, filters: list[dict]) -> list[dict]:
        if not self.ws:
            await self.connect()
        
        sub_id = f"fetch-{id(filters)}"
        message = json.dumps(["REQ", sub_id, *filters])
        await self.ws.send(message)
        
        events = []
        while True:
            response = await self.ws.recv()
            data = json.loads(response)
            
            if data[0] == "EVENT" and data[1] == sub_id:
                events.append(data[2])
            elif data[0] == "EOSE":
                break
        
        # Subscription beenden
        await self.ws.send(json.dumps(["CLOSE", sub_id]))
        return events
    
    async def listen(self):
        while True:
            try:
                message = await self.ws.recv()
                data = json.loads(message)
                
                if data[0] == "EVENT":
                    sub_id = data[1]
                    event = data[2]
                    if sub_id in self.subscriptions:
                        await self.subscriptions[sub_id](event)
            except websockets.ConnectionClosed:
                await self.connect()
```

### main.py

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from sse_starlette.sse import EventSourceResponse
from contextlib import asynccontextmanager
import asyncio
import json

from .models import IdeaCreate, SearchQuery, IdeaResponse
from .qdrant_service import init_collection, store_idea, search_similar, find_related
from .nostr_client import NostrClient
from .embedding_service import create_embedding

# Event Queue für SSE
event_queues: list[asyncio.Queue] = []
nostr_client: NostrClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global nostr_client
    
    # Startup
    init_collection()
    nostr_client = NostrClient()
    await nostr_client.connect()
    
    # Subscribe für neue Ideas (kind 30023 oder custom)
    await nostr_client.subscribe(
        "ideas",
        [{"kinds": [30023], "#t": ["idea"]}],
        handle_new_idea
    )
    
    # Listener Task starten
    asyncio.create_task(nostr_client.listen())
    
    yield
    
    # Shutdown
    await nostr_client.close()

app = FastAPI(lifespan=lifespan)

# Static Files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

async def handle_new_idea(event: dict):
    # In Qdrant speichern
    references = [tag[1] for tag in event.get("tags", []) if tag[0] == "e"]
    
    store_idea(
        event_id=event["id"],
        content=event["content"],
        pubkey=event["pubkey"],
        created_at=event["created_at"],
        references=references
    )
    
    # An alle SSE Clients senden
    for queue in event_queues:
        await queue.put(event)

# HTML Endpoints (HTMX)
@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("frontend/index.html")

@app.get("/components/idea-card/{event_id}", response_class=HTMLResponse)
async def idea_card(event_id: str):
    # Hole Event Details und rendere Partial
    events = await nostr_client.fetch_events([{"ids": [event_id]}])
    if not events:
        raise HTTPException(404, "Idea not found")
    
    event = events[0]
    related = find_related(event_id, limit=3)
    
    # HTML Partial rendern
    return render_idea_card(event, related)

# API Endpoints
@app.post("/api/ideas")
async def create_idea(idea: IdeaCreate, request: Request):
    # Event wird vom Frontend signiert und gesendet
    # Hier nur Validierung und Indexierung
    pass

@app.get("/api/search")
async def search_ideas(q: str, limit: int = 10, pubkey: str = None):
    results = search_similar(q, limit=limit, pubkey_filter=pubkey)
    return {"results": results}

@app.get("/api/related/{event_id}")
async def get_related(event_id: str, limit: int = 5):
    results = find_related(event_id, limit=limit)
    return {"results": results}

# SSE Stream für Live Updates
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

# HTMX Partials
@app.get("/partials/search-results", response_class=HTMLResponse)
async def search_results_partial(q: str):
    if not q.strip():
        return "<div class='text-gray-500'>Suchbegriff eingeben...</div>"
    
    results = search_similar(q, limit=10)
    
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
    
    return f'''
    <article class="idea-detail">
        <p class="content">{event["content"]}</p>
        <div class="meta">
            <time>{event["created_at"]}</time>
            <span class="pubkey">{event["pubkey"][:16]}...</span>
        </div>
        {related_html}
    </article>
    '''
```

## Phase 3: Frontend Implementation

### index.html

```html
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IdeaFlow</title>
    
    <!-- Tailwind via CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    
    <!-- HTMX -->
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <script src="https://unpkg.com/htmx.org@1.9.10/dist/ext/sse.js"></script>
    
    <!-- Alpine.js -->
    <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
    
    <!-- Nostr Tools -->
    <script src="https://unpkg.com/nostr-tools@2.1.0/lib/nostr.bundle.js"></script>
    
    <style>
        [x-cloak] { display: none !important; }
        
        .idea-card {
            @apply p-4 bg-white rounded-lg shadow-sm border border-gray-100 
                   cursor-pointer transition-all hover:shadow-md hover:border-blue-200;
        }
        
        .idea-card .content {
            @apply text-gray-800 line-clamp-3;
        }
        
        .idea-card .meta {
            @apply mt-2 flex justify-between text-xs text-gray-500;
        }
    </style>
</head>
<body class="bg-gray-50 min-h-screen" x-data="ideaFlow()">
    
    <!-- Header -->
    <header class="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div class="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
            <h1 class="text-xl font-semibold text-gray-900">IdeaFlow</h1>
            
            <!-- Identity Status -->
            <div x-show="pubkey" class="flex items-center gap-2">
                <span class="w-2 h-2 bg-green-500 rounded-full"></span>
                <span class="text-sm text-gray-600" x-text="pubkey.slice(0, 8) + '...'"></span>
            </div>
            <button x-show="!pubkey" @click="generateKeys()" 
                    class="text-sm text-blue-600 hover:text-blue-800">
                Identität erstellen
            </button>
        </div>
    </header>
    
    <main class="max-w-4xl mx-auto px-4 py-6">
        
        <!-- Idee erfassen -->
        <section class="mb-8">
            <form @submit.prevent="submitIdea()" class="bg-white rounded-xl shadow-sm p-4">
                <textarea 
                    x-model="newIdea"
                    placeholder="Was denkst du gerade?"
                    class="w-full resize-none border-0 focus:ring-0 text-gray-800 placeholder-gray-400"
                    rows="3"
                ></textarea>
                <div class="flex justify-between items-center mt-2 pt-2 border-t border-gray-100">
                    <span class="text-xs text-gray-400" x-show="newIdea.length > 0" 
                          x-text="newIdea.length + ' Zeichen'"></span>
                    <button type="submit" 
                            :disabled="!newIdea.trim() || !pubkey"
                            class="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium
                                   disabled:opacity-50 disabled:cursor-not-allowed
                                   hover:bg-blue-700 transition-colors">
                        Erfassen
                    </button>
                </div>
            </form>
        </section>
        
        <!-- Semantische Suche -->
        <section class="mb-8">
            <div class="relative">
                <input type="search"
                       placeholder="Suche nach ähnlichen Ideen..."
                       class="w-full px-4 py-3 bg-white rounded-xl shadow-sm border-0
                              focus:ring-2 focus:ring-blue-500"
                       hx-get="/partials/search-results"
                       hx-trigger="keyup changed delay:300ms, search"
                       hx-target="#search-results"
                       name="q">
                <div class="absolute right-3 top-1/2 -translate-y-1/2">
                    <svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
                    </svg>
                </div>
            </div>
            <div id="search-results" class="mt-4 space-y-3"></div>
        </section>
        
        <!-- Zwei-Spalten Layout -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            
            <!-- Ideen Stream mit Live Updates -->
            <section>
                <h2 class="text-lg font-medium text-gray-900 mb-4">Neueste Ideen</h2>
                <div id="idea-stream" 
                     class="space-y-3"
                     hx-ext="sse"
                     sse-connect="/stream">
                    
                    <!-- SSE fügt hier neue Ideen ein -->
                    <template sse-swap="new-idea" hx-swap="afterbegin">
                        <!-- Wird dynamisch befüllt -->
                    </template>
                    
                    <!-- Bestehende Ideen laden -->
                    <div hx-get="/partials/recent-ideas" 
                         hx-trigger="load"
                         hx-swap="innerHTML">
                        <div class="animate-pulse space-y-3">
                            <div class="h-24 bg-gray-200 rounded-lg"></div>
                            <div class="h-24 bg-gray-200 rounded-lg"></div>
                        </div>
                    </div>
                </div>
            </section>
            
            <!-- Detail-Ansicht -->
            <section>
                <h2 class="text-lg font-medium text-gray-900 mb-4">Details</h2>
                <div id="idea-detail" class="bg-white rounded-xl shadow-sm p-6 min-h-[200px]">
                    <p class="text-gray-500 text-center">
                        Klicke auf eine Idee, um Details zu sehen
                    </p>
                </div>
            </section>
        </div>
        
    </main>
    
    <script>
    function ideaFlow() {
        return {
            pubkey: null,
            privateKey: null,
            newIdea: '',
            
            init() {
                // Keys aus localStorage laden
                const stored = localStorage.getItem('nostr_keys');
                if (stored) {
                    const keys = JSON.parse(stored);
                    this.pubkey = keys.pubkey;
                    this.privateKey = keys.privateKey;
                }
            },
            
            generateKeys() {
                const sk = window.NostrTools.generateSecretKey();
                const pk = window.NostrTools.getPublicKey(sk);
                
                this.privateKey = window.NostrTools.bytesToHex(sk);
                this.pubkey = pk;
                
                localStorage.setItem('nostr_keys', JSON.stringify({
                    pubkey: this.pubkey,
                    privateKey: this.privateKey
                }));
            },
            
            async submitIdea() {
                if (!this.newIdea.trim() || !this.pubkey) return;
                
                const event = {
                    kind: 30023,
                    pubkey: this.pubkey,
                    created_at: Math.floor(Date.now() / 1000),
                    tags: [
                        ['d', crypto.randomUUID()],
                        ['t', 'idea'],
                        ['client', 'ideaflow']
                    ],
                    content: this.newIdea
                };
                
                // Event ID berechnen
                event.id = window.NostrTools.getEventHash(event);
                
                // Signieren
                const skBytes = window.NostrTools.hexToBytes(this.privateKey);
                event.sig = window.NostrTools.signEvent(event, skBytes);
                
                // An Backend senden
                const response = await fetch('/api/ideas', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(event)
                });
                
                if (response.ok) {
                    this.newIdea = '';
                }
            }
        }
    }
    </script>
</body>
</html>
```

## Phase 4: Erweiterte Features

### Netzwerk-Visualisierung

Für die Graph-Darstellung der Ideen-Verbindungen:

```html
<!-- In index.html einfügen -->
<script src="https://unpkg.com/force-graph"></script>

<div id="network-graph" 
     hx-get="/api/network-data"
     hx-trigger="load"
     hx-swap="none"
     hx-on::after-request="renderGraph(event.detail.xhr.response)">
</div>

<script>
function renderGraph(data) {
    const graphData = JSON.parse(data);
    
    ForceGraph()
        (document.getElementById('network-graph'))
        .graphData(graphData)
        .nodeLabel('content_preview')
        .nodeColor(node => node.isOwn ? '#3b82f6' : '#9ca3af')
        .linkColor(() => '#e5e7eb')
        .onNodeClick(node => {
            htmx.ajax('GET', `/components/idea-card/${node.id}`, '#idea-detail');
        });
}
</script>
```

### Cluster-Erkennung Endpoint

```python
# In main.py hinzufügen

@app.get("/api/clusters")
async def get_clusters():
    from sklearn.cluster import KMeans
    import numpy as np
    
    # Alle Vektoren aus Qdrant holen
    client = get_client()
    points = client.scroll(
        collection_name=COLLECTION_NAME,
        limit=1000,
        with_vectors=True,
        with_payload=True
    )[0]
    
    if len(points) < 5:
        return {"clusters": []}
    
    vectors = np.array([p.vector for p in points])
    
    # Optimale Cluster-Anzahl (vereinfacht)
    n_clusters = min(5, len(points) // 3)
    
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
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
```

### Resonanz-Benachrichtigung

```python
# In main.py erweitern

async def check_resonance(new_event: dict, user_pubkey: str):
    """Prüft ob eine neue Idee mit eigenen Ideen resoniert"""
    
    similar = search_similar(
        new_event["content"],
        limit=3,
        pubkey_filter=user_pubkey
    )
    
    # Schwellwert für Resonanz
    resonant = [s for s in similar if s["score"] > 0.7]
    
    if resonant:
        return {
            "type": "resonance",
            "new_idea": new_event["id"],
            "matching_ideas": resonant
        }
    return None
```

## Deployment Checkliste

1. Docker Compose starten: `docker-compose up -d`
2. Qdrant Collection wird automatisch erstellt
3. Nostr Relay läuft auf Port 8080
4. Backend auf Port 8000
5. Frontend wird vom Backend ausgeliefert

### Produktions-Anpassungen

- HTTPS via nginx reverse proxy
- Nostr Relay: `pubkey_whitelist` konfigurieren
- Qdrant: Persistenz-Volume auf SSD
- Embedding Model: GPU-Support für schnellere Vektorisierung
- Rate Limiting im Backend

## Weiterentwicklung

**Kurzfristig:**
- Multi-Relay Support (eigener + öffentliche)
- Import bestehender Nostr-Identitäten
- Markdown-Support in Ideen

**Mittelfristig:**
- Browser-Extension für schnelles Erfassen
- Mobile PWA
- Verschlüsselte private Ideen (NIP-04)

**Langfristig:**
- Föderierte Cluster über Relay-Grenzen
- AI-gestützte Zusammenfassungen von Clustern
- Kollaborative Boards für Teams
