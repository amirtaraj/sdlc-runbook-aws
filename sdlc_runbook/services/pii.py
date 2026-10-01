"""Azure AI Language - PII entity recognition.

POST {endpoint}/language/:analyze-text?api-version=2023-04-01  (kind: PiiEntityRecognition)

Long text is split into documents of at most 5,120 characters, sent 5 per request (the
service's synchronous limits); entity offsets are mapped back onto the full text.
"""
from dataclasses import dataclass

from ..config import ServiceEndpoint
from ..observability import MetricsRecorder
from .chunking import split_text
from .http import ServiceHttpClient

API_VERSION = "2023-04-01"
MAX_DOC_CHARS = 5_000
MAX_DOCS_PER_REQUEST = 5


@dataclass(frozen=True)
class PiiEntity:
    category: str
    confidence: float
    offset: int   # into the full text
    length: int


class PiiClient:
    def __init__(self, config: ServiceEndpoint, timeout: float, metrics: MetricsRecorder | None = None, transport=None):
        headers = {"Ocp-Apim-Subscription-Key": config.api_key} if config.api_key else {}
        self._http = ServiceHttpClient("pii", config.endpoint, headers, timeout, metrics, transport)

    def detect(self, text: str, min_confidence: float = 0.6) -> list[PiiEntity]:
        chunks = split_text(text, MAX_DOC_CHARS)
        entities: list[PiiEntity] = []
        for batch_start in range(0, len(chunks), MAX_DOCS_PER_REQUEST):
            batch = chunks[batch_start:batch_start + MAX_DOCS_PER_REQUEST]
            body = self._http.post(
                "analyzeText",
                "/language/:analyze-text",
                params={"api-version": API_VERSION},
                json={
                    "kind": "PiiEntityRecognition",
                    "parameters": {"modelVersion": "latest"},
                    "analysisInput": {"documents": [
                        {"id": str(batch_start + i), "language": "en", "text": chunk}
                        for i, (_, chunk) in enumerate(batch)
                    ]},
                },
            )
            offsets = {str(batch_start + i): off for i, (off, _) in enumerate(batch)}
            for doc in body.get("results", {}).get("documents", []):
                base = offsets.get(str(doc.get("id")), 0)
                for e in doc.get("entities", []):
                    confidence = float(e.get("confidenceScore", 0))
                    if confidence >= min_confidence:
                        entities.append(PiiEntity(e["category"], confidence,
                                                  base + int(e.get("offset", 0)), int(e.get("length", 0))))
        return sorted(entities, key=lambda e: e.offset)
