# IdeaFlow

Dezentrale Ideen-Management-Webapp mit semantischer Suche und Nostr-Protokoll.

## Features

- **Dezentrale Identität** - Nostr-Schlüsselpaare (secp256k1), kein zentraler Account
- **Semantische Suche** - Vektorbasierte Ähnlichkeitssuche mit Qdrant
- **Ideen-Netzwerk** - Visualisierung als interaktiver Graph
- **Cluster-Analyse** - Automatische Gruppierung verwandter Ideen
- **Referenzen** - Ideen miteinander verknüpfen (bidirektional)
- **Export** - JSON/Markdown Download mit Zeitfilter
- **Zeitfilter** - Ideen nach Zeitraum filtern (24h, 7d, 30d)
- **Schlüsselverwaltung** - Export/Import im nsec-Format

## Tech Stack

| Komponente | Technologie |
|------------|-------------|
| Backend | Python FastAPI |
| Frontend | HTML + HTMX + Alpine.js |
| Vector DB | Qdrant |
| Nostr Relay | strfry (Multi-Arch) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Styling | Tailwind CSS |

## Schnellstart

```bash
# Alle Services starten
docker-compose up -d

# Logs anzeigen
docker-compose logs -f backend

# Öffne http://localhost:8000
```

## Services

| Service | Port | Beschreibung |
|---------|------|--------------|
| Backend | 8000 | FastAPI + Static Files |
| Qdrant | 6333, 6334 | Vector DB (HTTP, gRPC) |
| Nostr Relay | 7777 | strfry WebSocket |

## Projektstruktur

```
ideaflow/
├── backend/
│   ├── main.py              # FastAPI App, SSE, Endpoints
│   ├── nostr_client.py      # WebSocket Client für Relay
│   ├── qdrant_service.py    # Vector-Operationen
│   ├── embedding_service.py # Text → Vector
│   └── models.py            # Pydantic Schemas
├── frontend/
│   ├── index.html           # SPA mit Alpine.js
│   └── static/
│       ├── app.js           # Frontend-Logik
│       └── styles.css       # Custom Styles
├── docker-compose.yml
├── strfry.conf              # Nostr Relay Config
└── CLAUDE.md                # AI-Coding Guidelines
```

## Architektur

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│   FastAPI   │────▶│   Qdrant    │
│  HTMX/Alpine│     │   Backend   │     │  Vector DB  │
└─────────────┘     └──────┬──────┘     └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │   strfry    │
                   │ Nostr Relay │
                   └─────────────┘
```

### Datenfluss

1. User erstellt Idee → signiert als Nostr Event (kind 30023)
2. Event wird an strfry Relay publiziert
3. Backend indexiert Content in Qdrant mit Vektor-Embedding
4. SSE streamt Updates an verbundene Clients

## API Endpoints

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| GET | `/` | Frontend SPA |
| POST | `/api/ideas` | Idee erstellen |
| GET | `/api/search?q=...&time=...` | Semantische Suche |
| GET | `/api/related/{id}` | Ähnliche Ideen |
| GET | `/api/clusters` | Cluster-Analyse |
| GET | `/api/network-data` | Graph-Daten |
| GET | `/api/export?format=json` | Export |
| GET | `/stream` | SSE Live-Updates |

## Entwicklung

```bash
# Backend lokal starten (nach docker-compose up qdrant nostr-relay)
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Nostr Event-Struktur

Ideen verwenden kind 30023 (replaceable long-form content):

```json
{
  "kind": 30023,
  "content": "Idee Text...",
  "tags": [
    ["d", "unique-id"],
    ["t", "idea"],
    ["client", "ideaflow"],
    ["e", "referenced-event-id"]
  ]
}
```

## Lizenz

MIT License - siehe [LICENSE](LICENSE)
