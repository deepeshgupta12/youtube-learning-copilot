import os
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_study_pack_from_youtube(monkeypatch):
    os.environ["ENV"] = "test"

    # mock transcript fetcher
    from app.services import transcript as transcript_mod

    def fake_fetch(video_id: str, language=None):
        return {
            "segments": [{"text": "hello world", "start": 0.0, "duration": 1.0}],
            "text": "hello world",
            "language": language or "en",
        }

    monkeypatch.setattr(transcript_mod, "fetch_youtube_transcript", fake_fetch)

    r = client.post("/study-packs/from-youtube", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "language": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["video_id"] == "dQw4w9WgXcQ"

    # since ENV=test makes celery eager, ingestion should be done
    job_id = body["job_id"]
    sp_id = body["study_pack_id"]

    g = client.get(f"/jobs/{job_id}")
    assert g.status_code == 200
    assert g.json()["status"] == "done"

    # check DB state via API? we don't have a /study-packs/{id} yet in V0.
    # For now: ensure job done is enough.
    assert isinstance(sp_id, int)
