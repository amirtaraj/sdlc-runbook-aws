"""Where runs (the conversation, every stage output and decision) are saved between requests.

RUN_STORE=memory    default; runs are lost when the API restarts (fine on a laptop)
RUN_STORE=dynamodb  one Amazon DynamoDB item per run, so runs survive restarts and updates

DynamoDB item: run_id (partition key), title, status, updated_at (for the history list) and
data: the run snapshot as gzip-compressed JSON, which keeps large runs under DynamoDB's
400 KB item limit. boto3 is imported lazily, so it is only needed for DynamoDB.
"""
import gzip
import json
import threading
from typing import Protocol

from ..exceptions import StorageError

SUMMARY_KEYS = ("run_id", "title", "status", "updated_at")
MAX_ITEM_BYTES = 390_000  # DynamoDB's limit is 400 KB per item, including attribute names


class RunStore(Protocol):
    def save(self, snapshot: dict) -> None: ...

    def load(self, run_id: str) -> dict | None: ...

    def list_summaries(self) -> list[dict]:
        """[{run_id, title, status, updated_at}, ...] for every saved run."""
        ...


class MemoryRunStore:
    def __init__(self):
        self._runs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def save(self, snapshot: dict) -> None:
        with self._lock:
            self._runs[snapshot["run_id"]] = json.loads(json.dumps(snapshot))

    def load(self, run_id: str) -> dict | None:
        with self._lock:
            data = self._runs.get(run_id)
            return json.loads(json.dumps(data)) if data else None

    def list_summaries(self) -> list[dict]:
        with self._lock:
            return [{k: r[k] for k in SUMMARY_KEYS} for r in self._runs.values()]


class DynamoRunStore:
    def __init__(self, table: str, region: str, client=None):
        self._table = table
        self._region = region
        self._client = client  # tests pass a fake with put_item / get_item / scan

    def _get_client(self):
        if self._client is None:
            try:
                import boto3
            except ImportError as e:  # pragma: no cover - depends on the environment
                raise StorageError("RUN_STORE=dynamodb needs boto3: pip install -r requirements.txt") from e
            self._client = boto3.client("dynamodb", region_name=self._region)
        return self._client

    def save(self, snapshot: dict) -> None:
        blob = gzip.compress(json.dumps(snapshot, ensure_ascii=False).encode("utf-8"))
        if len(blob) > MAX_ITEM_BYTES:
            raise StorageError(f"Run {snapshot['run_id']} is too large to save ({len(blob) // 1024} KB compressed).")
        item = {k: {"S": str(snapshot[k])} for k in SUMMARY_KEYS}
        item["data"] = {"B": blob}
        self._call("save", lambda c: c.put_item(TableName=self._table, Item=item))

    def load(self, run_id: str) -> dict | None:
        resp = self._call("load", lambda c: c.get_item(TableName=self._table, Key={"run_id": {"S": run_id}}))
        item = resp.get("Item")
        if not item:
            return None
        return json.loads(gzip.decompress(item["data"]["B"]).decode("utf-8"))

    def list_summaries(self) -> list[dict]:
        summaries, start_key = [], None
        while True:
            kwargs = {"TableName": self._table, "ProjectionExpression": "run_id, title, #s, updated_at",
                      "ExpressionAttributeNames": {"#s": "status"}}
            if start_key:
                kwargs["ExclusiveStartKey"] = start_key
            resp = self._call("list", lambda c: c.scan(**kwargs))
            summaries += [{k: item[k]["S"] for k in SUMMARY_KEYS if k in item} for item in resp.get("Items", [])]
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                return summaries

    def _call(self, action: str, fn):
        try:
            return fn(self._get_client())
        except StorageError:
            raise
        except Exception as e:  # botocore ClientError and credential errors
            response = getattr(e, "response", None)
            code = response.get("Error", {}).get("Code") if isinstance(response, dict) else type(e).__name__
            hints = {
                "ResourceNotFoundException": f"table '{self._table}' doesn't exist in {self._region}",
                "AccessDeniedException": "the IAM role lacks DynamoDB permission on the table",
                "NoCredentialsError": "no AWS credentials (attach the IAM role, or aws configure / aws sso login)",
            }
            raise StorageError(f"DynamoDB {action} failed: {hints.get(code, code or str(e))}.") from e
