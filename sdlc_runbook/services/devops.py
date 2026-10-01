"""Azure DevOps REST - work item creation, used by the "Publish backlog" simulated action.

POST {org_url}/{project}/_apis/wit/workitems/$Task?api-version=7.1   (JSON Patch body)
Auth: Basic with an empty user name and a PAT, as Azure DevOps expects.
"""
import base64
import html
from dataclasses import dataclass

from ..config import ServiceEndpoint
from ..observability import MetricsRecorder
from .http import ServiceHttpClient

API_VERSION = "7.1"


@dataclass(frozen=True)
class WorkItem:
    id: int
    title: str
    url: str


class DevOpsClient:
    def __init__(self, config: ServiceEndpoint, project: str, timeout: float,
                 metrics: MetricsRecorder | None = None, transport=None):
        headers = {}
        if config.api_key:
            token = base64.b64encode(f":{config.api_key}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"
        self._project = project
        self._http = ServiceHttpClient("devops", config.endpoint, headers, timeout, metrics, transport)

    def create_task(self, title: str, description_html: str, tags: list[str], estimate_hours: float | None) -> WorkItem:
        patch = [
            {"op": "add", "path": "/fields/System.Title", "value": title[:255]},
            {"op": "add", "path": "/fields/System.Description", "value": description_html},
            {"op": "add", "path": "/fields/System.Tags", "value": "; ".join(tags)},
        ]
        if estimate_hours is not None:
            patch.append({"op": "add", "path": "/fields/Microsoft.VSTS.Scheduling.OriginalEstimate", "value": estimate_hours})
        body = self._http.post(
            "createWorkItem",
            f"/{self._project}/_apis/wit/workitems/$Task",
            params={"api-version": API_VERSION},
            json=patch,
            headers={"Content-Type": "application/json-patch+json"},
        )
        url = body.get("_links", {}).get("html", {}).get("href") or body.get("url", "")
        return WorkItem(int(body["id"]), body.get("fields", {}).get("System.Title", title), url)


def task_description_html(description: str, acceptance_criteria: list[str]) -> str:
    items = "".join(f"<li>{html.escape(c)}</li>" for c in acceptance_criteria)
    return f"<p>{html.escape(description)}</p><p><b>Acceptance criteria</b></p><ul>{items}</ul>"
