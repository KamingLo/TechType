from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.future import select
from contextlib import asynccontextmanager

from extensions import init_db, get_async_session, engine
from models.score import Score
from controllers.game_controller import GameController

game_controller = GameController(get_async_session)

# --- Lifespan Normal ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("-----------------------------------------")
    print("Lifespan: Memulai aplikasi...")
    await init_db()
    
    print("Lifespan: Startup selesai.")
    print("-----------------------------------------")
    yield
    print("-----------------------------------------")
    print("Lifespan: Menutup aplikasi...")
    await engine.dispose()
    print("Lifespan: Shutdown selesai.")
    print("-----------------------------------------")

# --- FastAPI ---
app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/leaderboard")
async def get_leaderboard(session: AsyncSession = Depends(get_async_session)):
    try:
        result = await session.execute(
            select(Score).order_by(Score.wpm.desc()).limit(10)
        )
        scores = result.scalars().all()
        return [{"username": score.username, "wpm": score.wpm} for score in scores]
    except Exception as e:
        print(f"Error di /leaderboard: {e}")
        return {"error": "Gagal mengambil leaderboard."}

@app.websocket("/ws/play/{username}")
async def websocket_play(websocket: WebSocket, username: str):
    await websocket.accept()
    try:
        await game_controller.handle_connection(websocket, username)
    except WebSocketDisconnect:
        pass
