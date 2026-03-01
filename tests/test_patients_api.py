"""Tests for routers/patients.py — REST API with in-memory DB."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


@pytest.fixture
def client(session_factory):
    """TestClient with AsyncSessionLocal patched to use in-memory DB."""
    from dotenv import load_dotenv
    load_dotenv()

    with patch("routers.patients.AsyncSessionLocal", session_factory), \
         patch("db.init_db.create_tables", return_value=None):
        from main import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_create_patient_returns_201_data(client):
    resp = client.post("/api/patients", params={
        "doctor_id": "doc_001",
        "name": "李明",
        "gender": "男",
        "age": 45,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "李明"
    assert data["gender"] == "男"
    assert data["age"] == 45
    assert "id" in data


def test_create_patient_minimal(client):
    resp = client.post("/api/patients", params={
        "doctor_id": "doc_001",
        "name": "张三",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["gender"] is None
    assert data["age"] is None


def test_list_patients_empty(client):
    resp = client.get("/api/patients/doc_unknown")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_patients_returns_created(client):
    client.post("/api/patients", params={"doctor_id": "doc_001", "name": "李明"})
    client.post("/api/patients", params={"doctor_id": "doc_001", "name": "张三"})

    resp = client.get("/api/patients/doc_001")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert "李明" in names
    assert "张三" in names


def test_list_patients_isolated_by_doctor(client):
    client.post("/api/patients", params={"doctor_id": "doc_A", "name": "李明"})
    client.post("/api/patients", params={"doctor_id": "doc_B", "name": "张三"})

    resp_a = client.get("/api/patients/doc_A")
    assert len(resp_a.json()) == 1
    assert resp_a.json()[0]["name"] == "李明"

    resp_b = client.get("/api/patients/doc_B")
    assert len(resp_b.json()) == 1
    assert resp_b.json()[0]["name"] == "张三"


def test_list_patient_records_empty(client):
    create_resp = client.post("/api/patients", params={"doctor_id": "doc_001", "name": "李明"})
    patient_id = create_resp.json()["id"]

    resp = client.get(f"/api/patients/doc_001/{patient_id}/records")
    assert resp.status_code == 200
    assert resp.json() == []
