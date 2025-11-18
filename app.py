from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.future import select
from sqlalchemy import func
from contextlib import asynccontextmanager

from extensions import init_db, get_async_session, engine
from models.score import Score
from controllers.game_controller import GameController

game_controller = GameController(get_async_session)

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

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/leaderboard")
async def get_leaderboard():
    try:
        async with get_async_session() as session:
            max_wpm_alias = func.max(Score.wpm).label("max_wpm")

            query = (
                select(
                    Score.username,
                    max_wpm_alias
                )
                .group_by(Score.username)
                .order_by(max_wpm_alias.desc())
                .limit(10)
            )
            result = await session.execute(query)
            scores = result.all()

            return [{"username": row.username, "wpm": row.max_wpm} for row in scores]
    
    except Exception as e:
        print(f"Error di /leaderboard: {e}")
        return {"error": "Gagal mengambil leaderboard."}, 500

@app.websocket("/ws/play/{username}")
async def websocket_play(websocket: WebSocket, username: str):
    await websocket.accept()
    try:
        await game_controller.handle_connection(websocket, username)
    except WebSocketDisconnect:
        pass
