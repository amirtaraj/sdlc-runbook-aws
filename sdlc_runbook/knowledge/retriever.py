"""RAG retrieval: search the standards knowledge base, then screen results for injected instructions."""
from ..exceptions import ServiceError
from ..guardrails import Guard
from ..services import KnowledgeBaseClient, KnowledgeDoc


class Retriever:
    def __init__(self, kb: KnowledgeBaseClient, guard: Guard, top: int = 4):
        self._kb = kb
        self._guard = guard
        self._top = top

    def retrieve(self, query: str) -> list[KnowledgeDoc]:
        """Best-effort: if search is down the stage still runs, just without grounding."""
        try:
            docs = self._kb.search(query, top=self._top)
        except ServiceError:
            return []
        return self._guard.screen_documents(docs)

    def by_category(self, category: str, top: int = 50) -> list[KnowledgeDoc]:
        """Every document in a category (e.g. all coding standards), screened, in id order."""
        try:
            docs = self._kb.search("*", top=top, category=category)
        except ServiceError:
            return []
        return sorted(self._guard.screen_documents(docs), key=lambda d: d.id)


def as_prompt_context(docs: list[KnowledgeDoc]) -> list[dict]:
    return [{"id": d.id, "title": d.title, "content": d.content} for d in docs]
