from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class IdeaCreate(BaseModel):
    content: str
    references: Optional[List[str]] = []


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
