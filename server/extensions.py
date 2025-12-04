import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import asynccontextmanager

# Lokasi database SQLite untuk game typing_race
DATABASE_URL = "sqlite+aiosqlite:///./database/typing_race.db"

# Engine async yang digunakan SQLAlchemy untuk berkomunikasi dengan SQLite
engine = create_async_engine(DATABASE_URL, echo=True)

# Session factory yang menghasilkan session async setiap kali dibutuhkan
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base dari SQLAlchemy untuk membuat model tabel
Base = declarative_base()

# Fungsi untuk membuat semua tabel saat aplikasi pertama kali dijalankan
async def init_db():
    """
    Membuat semua tabel di database.
    """
    import os
    os.makedirs(os.path.dirname(DATABASE_URL.split("///")[-1]), exist_ok=True)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Dependency injector untuk mengambil session database secara async
@asynccontextmanager
async def get_async_session() -> AsyncSession:
    """
    Dependency injector untuk mendapatkan sesi database async.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except:
            await session.rollback()
            raise
        finally:
            await session.close()