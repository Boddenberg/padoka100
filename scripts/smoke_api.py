import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Check:
    method: str
    path: str
    expected_statuses: tuple[int, ...] = (200,)


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("API_KEY", "")

CHECKS = (
    Check("GET", "/health"),
    Check("GET", "/api/v1/produtos", (200, 401, 503)),
    Check("GET", "/api/v1/dias-de-venda", (200, 401, 503)),
    Check("GET", "/api/v1/notificacoes", (200, 401, 503)),
)


def request_json(check: Check) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    req = Request(f"{BASE_URL}{check.path}", method=check.method, headers=headers)
    try:
        with urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else None
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = body
        return exc.code, parsed


def main() -> int:
    failures: list[str] = []
    for check in CHECKS:
        try:
            status, payload = request_json(check)
        except URLError as exc:
            failures.append(f"{check.method} {check.path}: connection failed: {exc.reason}")
            continue
        except TimeoutError:
            failures.append(f"{check.method} {check.path}: timeout")
            continue

        ok = status in check.expected_statuses
        print(f"{'OK' if ok else 'FAIL'} {check.method} {check.path} -> {status}")
        if not ok:
            failures.append(f"{check.method} {check.path}: unexpected status {status}: {payload}")

    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
