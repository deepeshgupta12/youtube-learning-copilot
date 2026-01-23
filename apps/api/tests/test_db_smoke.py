from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User


def test_db_select_1():
    db: Session = SessionLocal()
    try:
        r = db.execute(text("SELECT 1")).scalar_one()
        assert r == 1
    finally:
        db.close()


def test_db_crud_user():
    db: Session = SessionLocal()
    try:
        email = "test@example.com"

        # cleanup if exists
        db.query(User).filter(User.email == email).delete()
        db.commit()

        u = User(email=email)
        db.add(u)
        db.commit()
        db.refresh(u)

        assert u.id is not None

        u2 = db.query(User).filter(User.email == email).one()
        assert u2.id == u.id
    finally:
        db.query(User).filter(User.email == "test@example.com").delete()
        db.commit()
        db.close()
