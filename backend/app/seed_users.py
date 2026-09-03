from app.db.session import SessionLocal
from app.models.report import Report
# agar match/custody models bhi hain to unko bhi import karo

db = SessionLocal()
db.query(Report).delete()
db.commit()