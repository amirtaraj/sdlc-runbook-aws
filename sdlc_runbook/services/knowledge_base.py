"""Azure AI Search - the engineering-standards knowledge base used for RAG.

POST {endpoint}/indexes/{index}/docs/search?api-version=2024-07-01
Index fields: id, title, category, content (see data/knowledge_base/ for the source docs).
"""
from dataclasses import dataclass

from ..config import ServiceEndpoint
from ..observability import MetricsRecorder
from .http import ServiceHttpClient

API_VERSION = "2024-07-01"


@dataclass(frozen=True)
class KnowledgeDoc:
    id: str
    title: str
    category: str
    content: str
    score: float


class KnowledgeBaseClient:
    def __init__(self, config: ServiceEndpoint, index: str, timeout: float,
                 metrics: MetricsRecorder | None = None, transport=None):
        headers = {"api-key": config.api_key} if config.api_key else {}
        self._index = index
        self._http = ServiceHttpClient("search", config.endpoint, headers, timeout, metrics, transport)

    def search(self, query: str, top: int = 4, category: str | None = None) -> list[KnowledgeDoc]:
        """Ranked search; with `category`, only documents in that category (OData filter)."""
        body_in = {"search": query or "*", "top": top, "select": "id,title,category,content", "queryType": "simple"}
        if category:
            body_in["filter"] = f"category eq '{category.replace(chr(39), '')}'"
        body = self._http.post(
            "search",
            f"/indexes/{self._index}/docs/search",
            params={"api-version": API_VERSION},
            json=body_in,
        )
        return [
            KnowledgeDoc(d["id"], d.get("title", ""), d.get("category", ""), d.get("content", ""),
                         float(d.get("@search.score", 0)))
            for d in body.get("value", [])
        ]
