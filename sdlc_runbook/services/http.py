"""Shared HTTP helpers: timeouts, error mapping and per-call metrics for every external API."""
import time

import httpx

from ..exceptions import ServiceError
from ..observability import MetricsRecorder, ServiceCallRecord


class ServiceHttpClient:
    def __init__(self, service: str, base_url: str, headers: dict[str, str], timeout: float,
                 metrics: MetricsRecorder | None = None, transport: httpx.BaseTransport | None = None):
        self.service = service
        self._metrics = metrics
        self._client = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout, transport=transport)

    def post(self, operation: str, path: str, *, params: dict | None = None, json=None,
             headers: dict[str, str] | None = None) -> dict:
        started = time.perf_counter()
        error = None
        try:
            resp = self._client.post(path, params=params, json=json, headers=headers)
            if resp.status_code >= 400:
                error = f"HTTP {resp.status_code}"
                raise ServiceError(f"{self.service} {operation} failed: HTTP {resp.status_code} {resp.text[:200]}")
            try:
                return resp.json()
            except ValueError as e:
                error = "invalid_json"
                raise ServiceError(f"{self.service} {operation} returned a non-JSON response.") from e
        except httpx.HTTPError as e:
            error = type(e).__name__
            raise ServiceError(f"{self.service} is unreachable ({type(e).__name__}). Is the service running?") from e
        finally:
            if self._metrics:
                self._metrics.record_service_call(ServiceCallRecord(
                    service=self.service,
                    operation=operation,
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    success=error is None,
                    error=error,
                ))
