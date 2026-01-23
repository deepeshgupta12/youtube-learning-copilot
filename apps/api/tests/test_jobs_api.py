from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_job_and_fetch_done_in_test_env():
    r = client.post("/jobs", json={"job_type": "sample_pipeline", "payload": {"x": 1}, "sleep_sec": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    job_id = body["job_id"]

    g = client.get(f"/jobs/{job_id}")
    assert g.status_code == 200
    job = g.json()
    assert job["ok"] is True
    assert job["status"] == "done"
    assert job["error"] is None
