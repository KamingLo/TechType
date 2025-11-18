from sqlalchemy import Column, Integer, String
from extensions import Base # Impor Base dari extensions.py

class Score(Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    wpm = Column(Integer)