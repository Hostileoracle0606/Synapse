from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.main import app


def test_openapi_routes_exist():
    response = TestClient(app).get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/api/health" in schema["paths"]
    assert "/api/notebooks" in schema["paths"]
    assert "/api/notebooks/{notebook_id}/chat" in schema["paths"]
