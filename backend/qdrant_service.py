from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, Range
)
import os
import uuid
import time
from typing import Optional
from embedding_service import create_embedding


def get_time_threshold(time_range: Optional[str]) -> Optional[int]:
    """Convert time range string to Unix timestamp threshold."""
    if not time_range or time_range == 'all':
        return None

    now = int(time.time())
    ranges = {
        '24h': 24 * 60 * 60,
        '7d': 7 * 24 * 60 * 60,
        '30d': 30 * 24 * 60 * 60
    }

    seconds = ranges.get(time_range)
    if seconds:
        return now - seconds
    return None


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
                   pubkey_filter: Optional[str] = None,
                   time_range: Optional[str] = None) -> list[dict]:
    client = get_client()
    query_vector = create_embedding(query)

    filter_conditions = []

    if pubkey_filter:
        filter_conditions.append(
            FieldCondition(
                key="pubkey",
                match=MatchValue(value=pubkey_filter)
            )
        )

    time_threshold = get_time_threshold(time_range)
    if time_threshold:
        filter_conditions.append(
            FieldCondition(
                key="created_at",
                range=Range(gte=time_threshold)
            )
        )

    search_filter = Filter(must=filter_conditions) if filter_conditions else None

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


def get_all_vectors_with_payload(limit: int = 1000, time_range: Optional[str] = None) -> list:
    client = get_client()

    scroll_filter = None
    time_threshold = get_time_threshold(time_range)
    if time_threshold:
        scroll_filter = Filter(
            must=[
                FieldCondition(
                    key="created_at",
                    range=Range(gte=time_threshold)
                )
            ]
        )

    points, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        limit=limit,
        scroll_filter=scroll_filter,
        with_vectors=True,
        with_payload=True
    )
    return points


def find_referencing_ideas(event_id: str) -> list[dict]:
    """Find ideas that reference the given event_id."""
    client = get_client()

    points, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        limit=100,
        with_payload=True
    )

    referencing = []
    for point in points:
        refs = point.payload.get("references", [])
        if event_id in refs:
            referencing.append({
                "event_id": point.payload.get("nostr_event_id", str(point.id)),
                **point.payload
            })

    return referencing
