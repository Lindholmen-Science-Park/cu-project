from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Location:
    name: str
    address: Optional[str] = None
    lng_lat: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["Location"]:
        if not data:
            return None
        return cls(
            name=str(data.get("name", "")),
            address=data.get("address"),
            lng_lat=data.get("lng_lat"),
        )


@dataclass
class ResultItem:
    id: str
    title: str
    link: str
    image_url_thumbnail: Optional[str] = None
    image_url_large: Optional[str] = None
    location: Optional[Location] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResultItem":
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            link=str(data.get("link", "")),
            image_url_thumbnail=data.get("image_url_thumbnail"),
            image_url_large=data.get("image_url_large"),
            location=Location.from_dict(data.get("location") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"id": self.id, "title": self.title, "link": self.link}
        if self.image_url_thumbnail:
            d["imageUrlThumbnail"] = self.image_url_thumbnail
        if self.image_url_large:
            d["imageUrlLarge"] = self.image_url_large
        if self.location:
            d["location"] = {
                "name": self.location.name,
                "address": self.location.address,
                "lngLat": self.location.lng_lat,
            }
        return d


@dataclass
class ResponseMeta:
    confidence: float = 0.0
    retrieval_source: str = ""
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["ResponseMeta"]:
        if not data:
            return None
        return cls(
            confidence=float(data.get("confidence", 0.0)),
            retrieval_source=str(data.get("retrieval_source", "")),
            tokens_used=data.get("tokens_used"),
            latency_ms=data.get("latency_ms"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confidence": self.confidence,
            "retrievalSource": self.retrieval_source,
            "tokensUsed": self.tokens_used,
            "latencyMs": self.latency_ms,
        }


@dataclass
class AgentResponse:
    response_text: str
    results: List[ResultItem] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    meta: Optional[ResponseMeta] = None
    session_id: Optional[str] = None
    session_new: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentResponse":
        results_raw = data.get("results") or []
        errors_raw = data.get("errors") or []
        return cls(
            response_text=str(data.get("response_text", "")),
            results=[ResultItem.from_dict(r) for r in results_raw if isinstance(r, dict)],
            errors=[str(e) for e in errors_raw],
            meta=ResponseMeta.from_dict(data.get("meta") or {}),
            session_id=data.get("session_id"),
            session_new=bool(data.get("session_new", False)),
        )

    @classmethod
    def from_json(cls, raw: str) -> "AgentResponse":
        return cls.from_dict(json.loads(raw))

    def to_event_payload(
        self,
        avatar_id: str,
        session_id: str,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the payload dict for an ai.agent.response event.

        ``language`` is the language code (``"en"`` / ``"sv"``) we asked the
        API to reply in. The frontend uses it to drive the TTS voice on the
        per-message "Listen" button (e.g. so a Swedish reply is spoken with
        the Swedish voice rather than the UI's current locale's voice).
        """
        payload: Dict[str, Any] = {
            "avatarId": avatar_id,
            "sessionId": session_id,
            "text": self.response_text,
            "results": [r.to_dict() for r in self.results],
        }
        if language:
            payload["language"] = language
        if self.meta:
            payload["meta"] = self.meta.to_dict()
        return payload
