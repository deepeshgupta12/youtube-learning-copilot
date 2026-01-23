import os
from starlette.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.study_pack import StudyPack

client = TestClient(app)


def test_get_study_pack_404():
    r = client.get("/study-packs/99999999")
    assert r.status_code == 404


def test_get_study_pack_ok():
    os.environ["ENV"] = "test"

    db = SessionLocal()
    sp = StudyPack(
        source_type="youtube",
        source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="Test",
        status="ingested",
        source_id="dQw4w9WgXcQ",
        language="en",
        meta_json='{"k":"v"}',
        transcript_json='{"segments":[{"text":"hello","start":0.0,"duration":1.0}]}',
        transcript_text="hello",
        error=None,
    )
    db.add(sp)
    db.commit()
    db.refresh(sp)

    r = client.get(f"/study-packs/{sp.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["study_pack"]["id"] == sp.id
    assert body["study_pack"]["status"] == "ingested"