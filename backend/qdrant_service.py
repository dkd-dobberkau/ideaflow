from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue
)
import os
import uuid
from typing import Optional
from embedding_service import create_embedding


def event_id_to_uuid(event_id: str) -> str:
    """Convert a hex event ID to a valid UUID for Qdrant."""
    # Use first 32 chars of event_id (or pad if shorter) to create UUID
    hex_str = event_id[:32].ljust(32, '0')
    return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}"

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
    point_id = event_id_to_uuid(event_id)

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=point_id,
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

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=limit,
        query_filter=search_filter,
        with_payload=True
    )

    return [
        {
            "event_id": hit.payload.get("nostr_event_id", str(hit.id)),
            "score": hit.score,
            **hit.payload
        }
        for hit in results.points
    ]


def find_related(event_id: str, limit: int = 5) -> list[dict]:
    client = get_client()
    point_id = event_id_to_uuid(event_id)

    points = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[point_id],
        with_vectors=True
    )

    if not points:
        return []

    vector = points[0].vector

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=limit + 1,
        with_payload=True
    )

    return [
        {
            "event_id": hit.payload.get("nostr_event_id", str(hit.id)),
            "score": hit.score,
            **hit.payload
        }
        for hit in results.points
        if hit.id != point_id
    ][:limit]


def get_idea_by_event_id(event_id: str) -> Optional[dict]:
    """Get a single idea by its Nostr event ID."""
    client = get_client()
    point_id = event_id_to_uuid(event_id)

    points = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=[point_id],
        with_payload=True
    )

    if not points:
        return None

    return {
        "event_id": points[0].payload.get("nostr_event_id", str(points[0].id)),
        **points[0].payload
    }


def get_all_vectors_with_payload(limit: int = 1000) -> list:
    client = get_client()
    points, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        limit=limit,
        with_vectors=True,
        with_payload=True
    )
    return points
