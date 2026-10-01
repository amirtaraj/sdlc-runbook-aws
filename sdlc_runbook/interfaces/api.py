"""Web API for the chat UI.

  python -m uvicorn sdlc_runbook.interfaces.api:create_app --factory --port 8000

Every /runs and /metrics route requires a signed-in user (mock or Entra ID, see auth/)
and checks their role. Sessions live in memory (enough for the MVP); the trace log,
audit log, LLM-call log and output documents are on disk. If frontend/dist exists it is
served at /.
"""
import logging
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..auth import APPROVER, VIEWER, Principal, build_authenticator
from ..bootstrap import SessionFactory
from ..config import PROJECT_ROOT, Settings
from ..documents import MAX_UPLOAD_BYTES, extract_text
from ..exceptions import (AgentError, AuthError, DocumentError, GuardrailViolation, InvalidAction, ServiceError,
                          StorageError)
from ..persistence import RunStore
from ..guardrails.guard import MAX_INPUT_CHARS
from ..pipeline import RunSession, RunStatus

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
logger = logging.getLogger("uvicorn.error")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self' https://login.microsoftonline.com; frame-src https://login.microsoftonline.com; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
}


# ---- request / response models ---------------------------------------------

class DocumentSource(BaseModel):
    """The uploaded document a requirement came from (text itself is in requirement_text)."""

    filename: str = Field(max_length=200)
    kind: str = Field(max_length=20)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pages: int | None = None
    chars: int
    redacted: bool = False


class StartRunRequest(BaseModel):
    requirement_text: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    source: DocumentSource | None = None
    tech_stack_id: str | None = Field(default=None, max_length=80)


class TechStackRef(BaseModel):
    id: str
    name: str


class DocumentExtractView(BaseModel):
    filename: str
    kind: str
    sha256: str
    size_bytes: int
    pages: int | None
    chars: int
    text: str
    blocked_reasons: list[str]       # cannot be fixed by redaction: remove from the document
    pii_categories: list[str]        # personal data found; the user may continue with redacted_text
    redacted_text: str | None


class EditRequest(BaseModel):
    correction_text: str = Field(min_length=1, max_length=5_000)


class ApproveRequest(BaseModel):
    override_reason: str | None = Field(default=None, max_length=2_000)


class GateView(BaseModel):
    check: str
    args: str
    description: str
    passed: bool
    detail: str


class StageRecordView(BaseModel):
    stage: str
    output: dict
    decision: str
    edit_note: str | None
    actor: str
    gates: list[GateView]
    gate_override: str | None
    references: list[dict]
    pii_flags: list[str]


class PublishedItemView(BaseModel):
    task_id: str
    work_item_id: int
    title: str
    url: str


class RunSummary(BaseModel):
    run_id: str
    title: str
    status: RunStatus
    updated_at: datetime


class RunView(RunSummary):
    requirement_text: str
    source: DocumentSource | None
    tech_stack: TechStackRef | None
    spec_pack_available: bool
    created_by: str
    stages: list[str]
    stage: str | None           # the stage currently pending (or failed / rejected)
    deployment: str | None
    output: dict | None         # the pending stage's output
    refusal: str | None         # the agent's reason, if the pending output is a refusal
    gates: list[GateView]       # quality-gate results for the pending output
    references: list[dict]      # knowledge-base docs the pending stage was grounded on
    pii_flags: list[str]        # PII categories found in the pending output (for the reviewer)
    edit_notes: list[str]       # corrections applied so far to the pending stage
    clarifications: list[str]
    history: list[StageRecordView]
    published: list[PublishedItemView]
    error: str | None
    agent_seconds: float
    usage: dict
    created_at: datetime
    document_markdown: str | None


def to_summary(s: RunSession) -> RunSummary:
    return RunSummary(run_id=s.run_id, title=s.title, status=s.status, updated_at=s.updated_at)


def to_view(s: RunSession) -> RunView:
    agent = s.current_agent
    pending = s.status is RunStatus.PENDING_APPROVAL
    return RunView(
        **to_summary(s).model_dump(),
        requirement_text=s.requirement_text,
        source=DocumentSource(**s.source) if s.source else None,
        tech_stack=TechStackRef(id=s.tech_stack["id"], name=s.tech_stack["name"]) if s.tech_stack else None,
        spec_pack_available=s.spec_pack_path is not None,
        created_by=s.created_by,
        stages=s.stages,
        stage=s.current_stage,
        deployment=agent.deployment if agent else None,
        output=s.current_output,
        refusal=s.current_refusal if pending else None,
        gates=[GateView(**vars(g)) for g in s.current_gates] if pending else [],
        references=s.current_references if pending else [],
        pii_flags=s.current_pii_flags if pending else [],
        edit_notes=s.edit_notes,
        clarifications=s.clarifications,
        history=[StageRecordView(**{**vars(r), "gates": [GateView(**vars(g)) for g in r.gates]}) for r in s.history],
        published=[PublishedItemView(**vars(p)) for p in s.published],
        error=s.error,
        agent_seconds=round(s.agent_seconds, 1),
        usage=s.usage,
        created_at=s.created_at,
        document_markdown=(s.document_path.read_text(encoding="utf-8")
                           if s.document_path and s.document_path.is_file() else None),
    )


# ---- session store -----------------------------------------------------------

class SessionStore:
    """Live runs cached in memory, saved to the run store (memory or DynamoDB) after every
    action, and loaded from it on demand, e.g. after a restart. One lock per run so a run
    never has two actions in flight."""

    def __init__(self, run_store: RunStore, restore: Callable[[dict], RunSession]):
        self._run_store = run_store
        self._restore = restore
        self._sessions: dict[str, RunSession] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._mutex = threading.Lock()

    def add(self, session: RunSession) -> None:
        with self._mutex:
            self._sessions[session.run_id] = session
            self._locks[session.run_id] = threading.Lock()
        self.save(session)

    def get(self, run_id: str) -> RunSession:
        with self._mutex:
            if run_id in self._sessions:
                return self._sessions[run_id]
        try:
            data = self._run_store.load(run_id)
        except StorageError as e:
            raise HTTPException(503, str(e)) from e
        if data is None:
            raise HTTPException(404, f"Run {run_id} not found.")
        session = self._restore(data)
        with self._mutex:
            self._locks.setdefault(run_id, threading.Lock())
            return self._sessions.setdefault(run_id, session)

    def summaries(self) -> list[RunSummary]:
        """Every saved run, newest first; live runs override their saved summary."""
        try:
            saved = {r["run_id"]: RunSummary(**r) for r in self._run_store.list_summaries()}
        except StorageError as e:
            logger.warning("Could not list saved runs: %s", e)
            saved = {}
        with self._mutex:
            live = {sid: to_summary(s) for sid, s in self._sessions.items()}
        merged = {**saved, **live}
        return sorted(merged.values(), key=lambda r: r.updated_at, reverse=True)

    def save(self, session: RunSession) -> None:
        try:
            self._run_store.save(session.snapshot())
        except StorageError as e:
            # The run keeps working in memory; it just won't survive a restart.
            logger.warning("Could not save run %s: %s", session.run_id, e)

    def act(self, run_id: str, action: Callable[[RunSession], None]) -> RunView:
        session = self.get(run_id)
        lock = self._locks[run_id]
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "This run is already processing a request.")
        try:
            action(session)
        except InvalidAction as e:
            raise HTTPException(409, str(e)) from e
        except (AgentError, ServiceError):
            pass  # recorded on session.error / status; the UI shows it with a retry option
        finally:
            lock.release()
            self.save(session)
        return to_view(session)


# ---- app -------------------------------------------------------------------

def create_app(factory: SessionFactory | None = None) -> FastAPI:
    factory = factory or SessionFactory(Settings.from_env())
    settings, audit = factory.settings, factory.audit
    authenticator = build_authenticator(settings.app_auth)
    store = SessionStore(factory.run_store, factory.restore)
    app = FastAPI(title="AI SDLC Runbook")
    logger.info("Model provider: %s (%s) | model auth: %s | app sign-in: %s", settings.llm_provider,
                settings.default_deployment, settings.describe_auth(), authenticator.mode)

    # ---- cross-cutting: security headers, error mapping, auth -----------------

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    @app.exception_handler(GuardrailViolation)
    def guardrail_blocked(request: Request, exc: GuardrailViolation):
        return JSONResponse(status_code=422, content={"detail": {"code": "guardrail_blocked", "reasons": exc.reasons}})

    @app.exception_handler(AuthError)
    def auth_failed(request: Request, exc: AuthError):
        audit.log("auth_denied", actor="anonymous", outcome="denied", path=request.url.path, reason=str(exc))
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    def current_user(authorization: Annotated[str | None, Header()] = None) -> Principal:
        return authenticator.authenticate(authorization)

    def require(role: str):
        def check(request: Request, user: Annotated[Principal, Depends(current_user)]) -> Principal:
            if not user.has_role(role):
                audit.log("permission_denied", actor=user.actor, outcome="denied", path=request.url.path, needed=role)
                raise HTTPException(403, f"This action needs the {role} role.")
            return user
        return check

    Viewer = Annotated[Principal, Depends(require(VIEWER))]
    Approver = Annotated[Principal, Depends(require(APPROVER))]

    def act(run_id: str, user: Principal, action: str, fn: Callable[[RunSession], None]) -> RunView:
        view = store.act(run_id, fn)
        audit.log(action, actor=user.actor, run_id=run_id, outcome="failed" if view.error else "success",
                  stage=view.stage, status=view.status.value)
        return view

    # ---- public ------------------------------------------------------------------

    @app.get("/health")
    def health() -> dict:
        # Reports *which* methods are configured, never the credentials themselves.
        return {
            "status": "ok",
            "model_provider": settings.llm_provider,
            "model_auth": settings.resolved_auth,
            "app_auth": authenticator.mode,
            "deployment": settings.default_deployment,
            "services": {
                name: "local" if ep.is_local else "azure"
                for name, ep in (("content_safety", settings.content_safety), ("pii", settings.language),
                                 ("search", settings.search), ("devops", settings.devops))
            },
        }

    @app.get("/auth/config")
    def auth_config() -> dict:
        return authenticator.public_config()

    # ---- runbook -------------------------------------------------------------------

    @app.get("/runbook")
    def runbook(user: Viewer) -> dict:
        """Stage definitions from RUNBOOK.md, so the UI can render any stage generically."""
        return {
            "stages": [
                {"id": s.id, "title": s.title, "purpose": s.purpose, "edit_mode": s.edit_mode, "schema": s.schema,
                 "for_each": bool(s.for_each), "collect_as": s.collect_as if s.for_each else None,
                 "gates": [{"check": g.check, "args": g.args, "description": g.description} for g in s.gates]}
                for s in factory.runbook.stages
            ]
        }

    # ---- runs ----------------------------------------------------------------------
    # Plain `def` endpoints: FastAPI runs them in a thread pool, so slow model calls don't block others.

    @app.get("/me")
    def me(user: Annotated[Principal, Depends(current_user)]) -> dict:
        return {"name": user.name, "email": user.email, "roles": list(user.roles), "auth_type": user.auth_type}

    @app.post("/documents/extract", response_model=DocumentExtractView)
    async def extract_document(user: Approver, file: UploadFile = File(...)) -> DocumentExtractView:
        """Read an uploaded requirements document and screen it. The file is not stored."""
        data = await file.read(MAX_UPLOAD_BYTES + 1)  # cap memory use; extract_text rejects oversize
        try:
            doc = await run_in_threadpool(extract_text, file.filename or "", data)
        except DocumentError as e:
            audit.log("document_rejected", actor=user.actor, outcome="rejected",
                      filename=(file.filename or "")[:200], size_bytes=len(data), reason=str(e))
            raise HTTPException(422, str(e)) from e
        review = await run_in_threadpool(factory.guard.review_document, doc.text)
        audit.log("document_extracted", actor=user.actor,
                  outcome="blocked" if review.blocking else "success",
                  filename=doc.filename, kind=doc.kind, sha256=doc.sha256, size_bytes=doc.size_bytes,
                  pages=doc.pages, chars=doc.chars, pii_categories=review.pii_categories,
                  blocked=len(review.blocking))
        return DocumentExtractView(
            filename=doc.filename, kind=doc.kind, sha256=doc.sha256, size_bytes=doc.size_bytes,
            pages=doc.pages, chars=doc.chars, text=doc.text, blocked_reasons=review.blocking,
            pii_categories=review.pii_categories, redacted_text=review.redacted_text,
        )

    @app.get("/tech-stacks")
    def tech_stacks(user: Viewer) -> dict:
        return {"default": factory.tech_stacks.default_id, "stacks": factory.tech_stacks.list()}

    @app.post("/runs", response_model=RunView)
    def start_run(body: StartRunRequest, user: Approver) -> RunView:
        source = body.source.model_dump() if body.source else None
        try:
            session = factory.create(body.requirement_text.strip(), created_by=user.actor, source=source,
                                     tech_stack_id=body.tech_stack_id)
        except KeyError as e:
            raise HTTPException(422, f"Unknown tech stack '{body.tech_stack_id}'.") from e
        except GuardrailViolation as e:
            audit.log("run_blocked", actor=user.actor, outcome="blocked", reasons=e.reasons, source=source)
            raise
        store.add(session)
        audit.log("run_created", actor=user.actor, run_id=session.run_id, source=source,
                  tech_stack=session.tech_stack["id"] if session.tech_stack else None)
        return act(session.run_id, user, "stage_run", lambda s: s.start())

    @app.get("/runs", response_model=list[RunSummary])
    def list_runs(user: Viewer) -> list[RunSummary]:
        return store.summaries()

    @app.get("/runs/{run_id}", response_model=RunView)
    def get_run(run_id: str, user: Viewer) -> RunView:
        return to_view(store.get(run_id))

    @app.post("/runs/{run_id}/approve", response_model=RunView)
    def approve(run_id: str, user: Approver, body: ApproveRequest | None = None) -> RunView:
        override = body.override_reason if body else None
        action = "stage_approve_override" if override else "stage_approve"
        return act(run_id, user, action, lambda s: s.approve(user.actor, override))

    @app.post("/runs/{run_id}/edit", response_model=RunView)
    def edit(run_id: str, body: EditRequest, user: Approver) -> RunView:
        try:
            return act(run_id, user, "stage_edit", lambda s: s.edit(body.correction_text, user.actor))
        except GuardrailViolation as e:
            audit.log("edit_blocked", actor=user.actor, run_id=run_id, outcome="blocked", reasons=e.reasons)
            raise

    @app.post("/runs/{run_id}/reject", response_model=RunView)
    def reject(run_id: str, user: Approver) -> RunView:
        return act(run_id, user, "stage_reject", lambda s: s.reject(user.actor))

    @app.post("/runs/{run_id}/retry", response_model=RunView)
    def retry(run_id: str, user: Approver) -> RunView:
        return act(run_id, user, "stage_retry", lambda s: s.retry())

    @app.post("/runs/{run_id}/publish", response_model=RunView)
    def publish(run_id: str, user: Approver) -> RunView:
        return act(run_id, user, "backlog_publish", lambda s: s.publish(user.actor))

    @app.get("/runs/{run_id}/document")
    def document(run_id: str, user: Viewer) -> Response:
        session = store.get(run_id)
        if session.document_path is None:
            raise HTTPException(409, "The document is available once the Tasks stage is approved.")
        if not session.document_path.is_file():
            raise HTTPException(404, "The document file is no longer on this server.")
        audit.log("document_download", actor=user.actor, run_id=run_id)
        return Response(
            session.document_path.read_text(encoding="utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{session.run_id}.md"'},
        )

    @app.get("/runs/{run_id}/spec-pack")
    def spec_pack(run_id: str, user: Viewer) -> Response:
        session = store.get(run_id)
        if session.spec_pack_path is None:
            raise HTTPException(409, "The spec pack is available once the Specification stage is approved.")
        if not session.spec_pack_path.is_file():
            raise HTTPException(404, "The spec pack file is no longer on this server.")
        audit.log("spec_pack_download", actor=user.actor, run_id=run_id)
        return Response(
            session.spec_pack_path.read_bytes(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{session.spec_pack_path.name}"'},
        )

    @app.get("/runs/{run_id}/documents/{stage}")
    def stage_document(run_id: str, stage: str, user: Viewer) -> Response:
        path = store.get(run_id).stage_documents.get(stage)
        if path is None or not path.is_file():
            raise HTTPException(404, f"No approved {stage} document for this run.")
        audit.log("document_download", actor=user.actor, run_id=run_id, stage=stage)
        return Response(
            path.read_text(encoding="utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{run_id}-{path.name}"'},
        )

    # ---- AgentOps ------------------------------------------------------------------

    @app.get("/metrics")
    def metrics(user: Viewer) -> dict:
        runs = store.summaries()
        by_status = {status.value: sum(1 for r in runs if r.status is status) for status in RunStatus}
        finished = by_status["completed"] + by_status["rejected"]
        return {
            "runs": {
                "total": len(runs),
                "by_status": by_status,
                "completion_rate": round(by_status["completed"] / finished, 3) if finished else None,
            },
            **factory.metrics.summary(),
        }

    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    return app
