from sqlalchemy import Column, Integer, String

from extensions import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)

    def __repr__(self) -> str:
        return f"<User {self.username}>"