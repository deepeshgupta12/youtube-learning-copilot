from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StudyPack(Base):
    __tablename__ = "study_packs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "video" | "playlist"
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
