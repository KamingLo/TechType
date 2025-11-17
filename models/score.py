from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
# Import Base dari extensions.py
from extensions import Base

class Score(Base):
    """
    Model untuk menyimpan skor pemain di leaderboard.
    """
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False)
    wpm = Column(Integer, nullable=False) # Words Per Minute
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Score(username='{self.username}', wpm={self.wpm})>"