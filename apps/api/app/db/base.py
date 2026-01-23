from app.db.base_class import Base  # noqa: F401

# Import all the models here so that Base has them registered
# This file should NOT be imported by models.
from app.models.user import User  # noqa: F401
from app.models.job import Job  # noqa: F401
from app.models.study_pack import StudyPack  # noqa: F401
from app.models.study_material import StudyMaterial  # noqa: F401