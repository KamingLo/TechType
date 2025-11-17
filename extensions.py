import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import asynccontextmanager

# Ganti nama database Anda dari 'techtype.db' ke 'typing_race.db'
# atau sesuaikan URL ini
DATABASE_URL = "sqlite+aiosqlite:///./database/typing_race.db"

engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Definisikan Base di sini agar bisa di-import oleh file model
Base = declarative_base()

async def init_db():
    """
    Membuat semua tabel di database.
    """
    async with engine.begin() as conn:
        # Perintah ini akan membuat tabel (Score, User)
        # berdasarkan semua model yang meng-import Base
        await conn.run_sync(Base.metadata.create_all)

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

# Jika Anda punya setup database lama di file ini, 
# Anda bisa menggabungkannya atau menggantinya dengan kode async ini.