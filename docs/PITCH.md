# IdeaFlow - Decentralized Idea Management

**What if your ideas could find each other?**

---

We built IdeaFlow in a weekend to explore a simple question: Can we combine **decentralized identity** with **semantic search** to create a new kind of idea management?

## The Problem

Traditional note-taking and idea management tools have two issues:

1. **Your data lives on someone else's server** - one company shutdown away from disappearing
2. **Search is keyword-based** - you need to remember exact words to find related thoughts

## Our Approach

**Decentralized Identity** via Nostr protocol
- Your identity is a cryptographic key pair you control
- Export it, import it anywhere - no account, no password, no vendor lock-in

**Semantic Search** via vector embeddings
- Search by *meaning*, not keywords
- "artificial intelligence" finds ideas about "machine learning" and "neural networks"
- Automatic clustering of related ideas

## The Stack (Refreshingly Simple)

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | HTMX + Alpine.js | No build step, no npm, just HTML |
| Backend | Python FastAPI | Fast, async, type-safe |
| Vector DB | Qdrant | Production-ready similarity search |
| Identity | Nostr (strfry relay) | Decentralized, multi-device |

**Zero JavaScript bundlers. Zero webpack configs. Just code.**

## What We Learned

1. **HTMX + Alpine.js** is production-ready for content-focused apps
2. **Vector search** makes "related content" actually useful
3. **Nostr** is more than crypto - it's a solid foundation for user-owned data

## Try It

```bash
git clone https://github.com/dkd-dobberkau/ideaflow
docker-compose up -d
# Open http://localhost:8000
```

---

*Built with FastAPI, HTMX, Alpine.js, Qdrant, and Nostr.*

*Interested in the intersection of CMS, decentralized tech, and semantic search? Let's talk.*

---

**#OpenSource #Nostr #SemanticSearch #HTMX #DecentralizedWeb #ContentManagement**
