"""Local services server. See __init__.py for the routes and the Azure contracts they mirror.

Binds to 127.0.0.1 only. Keys are not required (any value is accepted) because nothing
here leaves the machine; the runbook sends them anyway when configured.
"""
import itertools
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

from .injection_detector import detect_attack
from .pii_detector import detect_pii, redact
from .search_index import Bm25Index

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE = ROOT / "data" / "knowledge_base" / "standards.json"
WORK_ITEMS_LOG = ROOT / "logs" / "local_devops_work_items.jsonl"


def create_app(knowledge_base: Path = KNOWLEDGE_BASE, work_items_log: Path | None = WORK_ITEMS_LOG) -> FastAPI:
    app = FastAPI(title="SDLC Runbook - local services")
    index = Bm25Index.from_file(knowledge_base)
    work_item_ids = itertools.count(1001)
    lock = threading.Lock()

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "knowledge_base_docs": len(index.docs)}

    # ---- Azure AI Content Safety: Prompt Shields ------------------------------------
    @app.post("/contentsafety/text:shieldPrompt")
    async def shield_prompt(request: Request) -> dict:
        body = await request.json()
        return {
            "userPromptAnalysis": {"attackDetected": detect_attack(body.get("userPrompt", ""))},
            "documentsAnalysis": [{"attackDetected": detect_attack(d)} for d in body.get("documents", [])],
        }

    # ---- Azure AI Language: PII entity recognition -------------------------------------
    @app.post("/language/:analyze-text")
    async def analyze_text(request: Request) -> dict:
        body = await request.json()
        if body.get("kind") != "PiiEntityRecognition":
            raise HTTPException(400, "Only kind=PiiEntityRecognition is supported locally.")
        documents = []
        for doc in body.get("analysisInput", {}).get("documents", []):
            text = doc.get("text", "")
            entities = detect_pii(text)
            documents.append({
                "id": doc.get("id", "1"),
                "redactedText": redact(text, entities),
                "entities": [
                    {"text": e.text, "category": e.category, "offset": e.offset, "length": e.length,
                     "confidenceScore": e.confidence}
                    for e in entities
                ],
                "warnings": [],
            })
        return {"kind": "PiiEntityRecognitionResults",
                "results": {"documents": documents, "errors": [], "modelVersion": "local-heuristic-1"}}

    # ---- Azure AI Search: document search -------------------------------------------------
    @app.post("/indexes/{index_name}/docs/search")
    async def search(index_name: str, request: Request) -> dict:
        body = await request.json()
        top = max(1, min(int(body.get("top", 4)), 50))
        # Supports the one OData filter form the runbook uses: category eq '<name>'
        category = None
        if body.get("filter"):
            match = re.fullmatch(r"\s*category\s+eq\s+'([^']*)'\s*", body["filter"])
            if not match:
                raise HTTPException(400, "Only filters of the form category eq '<name>' are supported locally.")
            category = match.group(1)
        query = body.get("search", "")
        if category:
            docs = [d for d in index.docs if d.get("category") == category]
            ranked = dict((d["id"], s) for d, s in index.search(query, len(index.docs))) if query not in ("", "*") else {}
            results = sorted(((d, ranked.get(d["id"], 1.0)) for d in docs), key=lambda x: (-x[1], x[0]["id"]))[:top]
        else:
            results = index.search(query, top)
        return {
            "value": [
                {"@search.score": score, "id": d["id"], "title": d["title"], "category": d.get("category", ""),
                 "content": d["content"]}
                for d, score in results
            ]
        }

    # ---- Azure DevOps: create work item -----------------------------------------------------
    @app.post("/devops/{org}/{project}/_apis/wit/workitems/{work_item_type}")
    async def create_work_item(org: str, project: str, work_item_type: str, request: Request) -> dict:
        patch = await request.json()
        if not isinstance(patch, list):
            raise HTTPException(400, "Expected a JSON Patch document (a list of operations).")
        fields = {op["path"].removeprefix("/fields/"): op["value"] for op in patch
                  if op.get("op") == "add" and str(op.get("path", "")).startswith("/fields/")}
        if not fields.get("System.Title"):
            raise HTTPException(400, "System.Title is required.")
        with lock:
            item_id = next(work_item_ids)
        item = {
            "id": item_id,
            "rev": 1,
            "fields": {"System.WorkItemType": work_item_type.lstrip("$"), "System.State": "New",
                       "System.TeamProject": project, **fields},
            "url": f"http://127.0.0.1:8001/devops/{org}/{project}/_apis/wit/workItems/{item_id}",
            "_links": {"html": {"href": f"http://127.0.0.1:8001/devops/{org}/{project}/_workitems/edit/{item_id}"}},
        }
        if work_items_log:
            with lock:
                work_items_log.parent.mkdir(parents=True, exist_ok=True)
                with work_items_log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), **item}) + "\n")
        return item

    return app


app = create_app()
