"""
Importing all models here matters: SQLAlchemy's Base.metadata.create_all()
only creates tables for models that have been imported somewhere. If you
add a new model file and forget to import it here, its table silently
never gets created.
"""

from app.models.report import Report, ReportType, ReportStatus
from app.models.match import Match, MatchStatus
from app.models.custody import CustodyRecord

__all__ = [
    "Report", "ReportType", "ReportStatus",
    "Match", "MatchStatus",
    "CustodyRecord",
]