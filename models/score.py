from sqlalchemy import Column, Integer, String
from extensions import Base

class Score(Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    wpm = Column(Integer, nullable=False)
