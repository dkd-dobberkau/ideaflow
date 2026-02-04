# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

IdeaFlow is a decentralized idea management webapp combining personal sovereignty with emergent network thinking. Currently exists as a specification document (`ideaflow-spec.md`) - implementation not yet started.

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python FastAPI |
| Frontend | HTML + HTMX + Alpine.js (CDN, no build step) |
| Vector DB | Qdrant (semantic similarity search) |
| Event Store | nostr-rs-relay (decentralized data) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Styling | Tailwind CSS (CDN) |

## Common Commands

```bash
# Start all services (Qdrant, Nostr relay, Backend)
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop services
docker-compose down

# Backend development (after services are running)
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Architecture

### Decentralized Identity
- Uses Nostr protocol with secp256k1 keypairs
- Client-side key generation and event signing
- No centralized user database

### Data Flow
1. User creates idea → signed as Nostr event (kind 30023)
2. Event published to nostr-rs-relay
3. Backend indexes content in Qdrant with vector embedding
4. SSE streams updates to connected clients

### Semantic Search
- Text converted to 384-dim vectors via sentence-transformers
- Qdrant stores vectors with payload (pubkey, timestamp, references)
- Cosine similarity for finding related ideas

### Frontend Architecture
- Hypermedia-driven: HTMX handles partial HTML updates
- Alpine.js for reactive state (identity, forms)
- SSE subscription for live updates
- No bundler/transpiler needed

## Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| Backend | 8000 | FastAPI + static files |
| Qdrant | 6333, 6334 | HTTP, gRPC |
| Nostr Relay | 8080 | WebSocket |

## Key Files (After Implementation)

```
backend/
├── main.py              # FastAPI app, SSE, HTMX endpoints
├── nostr_client.py      # WebSocket client for relay
├── qdrant_service.py    # Vector operations
├── embedding_service.py # Text → vector conversion
└── models.py            # Pydantic schemas

frontend/
├── index.html           # Main SPA with Alpine.js
└── static/app.js        # Nostr key management
```

## Environment Variables

```
QDRANT_HOST=qdrant
QDRANT_PORT=6333
NOSTR_RELAY_URL=ws://nostr-relay:8080
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

## Nostr Event Structure

Ideas use kind 30023 (replaceable long-form content):
- `d` tag: unique identifier per user
- `t` tag: "idea" classification
- `e` tags: references to other events
