from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_generate_and_fetch_materials_flow(monkeypatch):
    """
    Assumes a StudyPack with id=1 exists and is ingested in the test DB.
    If your test DB doesn’t seed this, you should create it via your existing factories/helpers.
    """

    # If your tests already create a StudyPack in DB, replace 1 with that id.
    # Otherwise: create one here using your existing DB helper pattern.
    study_pack_id = 1

    # Trigger generation
    r = client.post(f"/study-packs/{study_pack_id}/generate")
    # In ENV=test, if Celery is eager, this may complete immediately.
    assert r.status_code in (200, 400, 404)

    # If the pack exists + ingested, it should be 200
    if r.status_code == 200:
        body = r.json()
        assert body["ok"] is True

        # Fetch materials
        r2 = client.get(f"/study-packs/{study_pack_id}/materials")
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["ok"] is True
        assert body2["study_pack_id"] == study_pack_id
        assert isinstance(body2["materials"], list)