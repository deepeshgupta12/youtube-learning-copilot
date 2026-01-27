# apps/api/app/worker/generate_tasks.py
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.study_material import StudyMaterial
from app.models.study_pack import StudyPack
from app.services.jobs import set_job_status, merge_job_payload
from app.services.study_materials import generate_and_store_all
from app.worker.celery_app import celery_app


KINDS = ["summary", "key_takeaways", "chapters", "flashcards", "quiz"]


@celery_app.task(name="generate.study_materials")
def generate_study_materials(job_id: int, study_pack_id: int) -> dict:
    db: Session = SessionLocal()
    try:
        # 1) Mark job running
        set_job_status(db, job_id, "running")

        # 2) Seed payload
        merge_job_payload(
            db,
            job_id,
            {
                "study_pack_id": study_pack_id,
                "progress": {"stage": "start", "done": 0, "total": len(KINDS)},
            },
        )

        # 3) Validate pack exists + ingested
        sp = db.query(StudyPack).filter(StudyPack.id == study_pack_id).first()
        if not sp:
            raise ValueError(f"StudyPack not found: {study_pack_id}")
        if sp.status != "ingested":
            raise ValueError(f"StudyPack not ingested yet (status={sp.status})")

        merge_job_payload(
            db,
            job_id,
            {"progress": {"stage": "generate_and_store", "done": 0, "total": len(KINDS)}},
        )

        # 4) Generate + store all 5 materials
        # generate_and_store_all handles openai->heuristic fallback and writes per-kind errors.
        result_meta = generate_and_store_all(db, study_pack_id) or {}

        merge_job_payload(
            db,
            job_id,
            {
                "progress": {"stage": "stored", "done": len(KINDS), "total": len(KINDS)},
                "provider": result_meta.get("provider"),
                "requested_provider": result_meta.get("requested_provider"),
                "openai_error": result_meta.get("openai_error"),
            },
        )

        # 5) Inspect rows and decide final job status
        rows = (
            db.query(StudyMaterial)
            .filter(StudyMaterial.study_pack_id == study_pack_id)
            .all()
        )

        by_kind = {r.kind: r for r in rows}
        missing = [k for k in KINDS if k not in by_kind]

        errors: list[dict] = []
        for k in KINDS:
            r = by_kind.get(k)
            if not r:
                continue
            if r.error:
                errors.append({"kind": k, "error": r.error})

        summary = {
            "total_kinds": len(KINDS),
            "rows_present": len(by_kind),
            "missing_kinds": missing,
            "error_count": len(errors),
            "errors": errors[:10],  # cap payload size
        }
        merge_job_payload(db, job_id, {"summary": summary, "progress": {"stage": "done"}})

        # If anything is missing => fail hard (should not happen)
        if missing:
            msg = f"Materials missing for kinds: {', '.join(missing)}"
            set_job_status(db, job_id, "failed", error=msg)
            return {"ok": False, "job_id": job_id, "study_pack_id": study_pack_id, "error": msg}

        # If there are per-kind errors, job is still 'done' but surface warning
        if errors:
            warn = f"{len(errors)} material(s) generated with warnings"
            set_job_status(db, job_id, "done", error=warn)
            return {
                "ok": True,
                "job_id": job_id,
                "study_pack_id": study_pack_id,
                "warnings": errors,
            }

        set_job_status(db, job_id, "done", error=None)
        return {"ok": True, "job_id": job_id, "study_pack_id": study_pack_id}

    except Exception as e:
        err = str(e)
        merge_job_payload(db, job_id, {"progress": {"stage": "failed"}, "error": err})
        set_job_status(db, job_id, "failed", error=err)
        # keep raise for celery visibility (your current behavior); if you want "no red celery trace",
        # change this to `return {"ok": False, ...}` instead of raising.
        raise
    finally:
        db.close()