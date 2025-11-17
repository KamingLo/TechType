import asyncio
from sqlalchemy.ext.asyncio import AsyncSession  # <- tambahkan ini
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.future import select
from typing import List, Dict
from contextlib import asynccontextmanager

from extensions import init_db, get_async_session, engine, AsyncSessionLocal, Base
from models.score import Score

# --- Matchmaking ---
waiting_players: List[WebSocket] = []
active_games: Dict[WebSocket, WebSocket] = {}

# --- Lifespan Normal ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("-----------------------------------------")
    print("Lifespan: Memulai aplikasi...")
    await init_db()

    # Tambahkan dummy leaderboard jika belum ada
    async with get_async_session() as session:
        async with session.begin():
            result = await session.execute(select(Score).limit(1))
            if result.first() is None:
                session.add_all([
                    Score(username="player_one", wpm=80),
                    Score(username="fast_typer", wpm=102),
                    Score(username="speedy", wpm=95),
                ])
                print("Lifespan: Dummy leaderboard ditambahkan.")
            else:
                print("Lifespan: Data leaderboard sudah ada.")

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
    websocket.state.username = username

    if not waiting_players:
        waiting_players.append(websocket)
        await websocket.send_json({"status": "waiting", "message": "Mencari lawan... (1/2)"})
        try:
            while websocket in waiting_players:
                await websocket.receive_text()  # ping/pong
        except WebSocketDisconnect:
            if websocket in waiting_players:
                waiting_players.remove(websocket)
            print(f"Pemain {username} disconnected saat menunggu.")
    else:
        player1 = waiting_players.pop(0)
        player2 = websocket
        active_games[player1] = player2
        active_games[player2] = player1

        player1_username = player1.state.username
        player2_username = player2.state.username

        await player1.send_json({
            "status": "matched",
            "message": f"Lawan ditemukan: {player2_username}!",
            "opponent": player2_username
        })
        await player2.send_json({
            "status": "matched",
            "message": f"Lawan ditemukan: {player1_username}!",
            "opponent": player1_username
        })

        try:
            while True:
                data = await websocket.receive_json()
                opponent = active_games.get(websocket)
                if opponent:
                    await opponent.send_json({"type": "progress", "data": data})

        except WebSocketDisconnect:
            print(f"Pemain {username} disconnected dari game.")
            other_player = active_games.pop(websocket, None)
            if not other_player:
                for p1, p2 in list(active_games.items()):
                    if p2 == websocket:
                        other_player = p1
                        break
            if other_player in active_games:
                active_games.pop(other_player)
            if other_player:
                try:
                    await other_player.send_json({
                        "status": "opponent_disconnected",
                        "message": f"{username} telah keluar dari permainan."
                    })
                except Exception as e:
                    print(f"Gagal mengirim pesan disconnect: {e}")
