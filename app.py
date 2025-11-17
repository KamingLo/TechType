import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.future import select
from typing import List, Dict
from contextlib import asynccontextmanager

# Import dari file extensions.py Anda
from extensions import (
    init_db,
    get_async_session,
    engine,
    AsyncSessionLocal,
    Base
)
# Import dari file models/score.py yang baru
from models.score import Score

# --- Matchmaking ---
waiting_players: List[WebSocket] = []
active_games: Dict[WebSocket, WebSocket] = {}

# --- BARU: Lifespan Manager (VERSI DEBUG) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manajer lifespan untuk menangani event startup dan shutdown.
    (Versi Debug: Kode database dimatikan sementara)
    """
    
    # --- SEMUA KODE DATABASE DI-COMMENT SEMENTARA UNTUK DEBUG ---
    print("-----------------------------------------")
    print("Lifespan: DEBUG: Mencoba STARTUP...")
    # print("Lifespan: Memulai aplikasi...")
    # await init_db()
    # async with AsyncSessionLocal() as session:
    #     async with session.begin():
    #         existing_data = await session.execute(select(Score).limit(1))
    #         if existing_data.first() is None:
    #             print("Lifespan: Menambahkan data leaderboard dummy...")
    #             session.add_all([
    #                 Score(username="player_one", wpm=80),
    #                 Score(username="fast_typer", wpm=102),
    #                 Score(username="speedy", wpm=95),
    #             ])
    #         else:
    #             print("Lifespan: Data leaderboard sudah ada.")
    # print("Lifespan: Startup selesai.")
    print("Lifespan: DEBUG: Startup Selesai (tanpa DB).")
    print("-----------------------------------------")

    yield # <-- Aplikasi berjalan di sini
    
    # --- SHUTDOWN ---
    print("-----------------------------------------")
    print("Lifespan: DEBUG: Mencoba SHUTDOWN...")
    # print("Lifespan: Menutup aplikasi...")
    # await engine.dispose()
    # print("Lifespan: Shutdown selesai.")
    print("Lifespan: DEBUG: Shutdown Selesai (tanpa DB).")
    print("-----------------------------------------")


# --- Aplikasi FastAPI ---
# Daftarkan 'lifespan' di sini
app = FastAPI(lifespan=lifespan)

# Setup untuk membaca file dari folder 'templates'
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """
    Menyajikan file index.html dari folder 'templates'.
    """
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/leaderboard")
async def get_leaderboard():
    """
    Endpoint API async untuk mengambil data leaderboard.
    """
    # Catatan: Ini mungkin akan error jika tabel belum ada,
    # tapi yang penting server-nya bisa jalan dulu.
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(Score).order_by(Score.wpm.desc()).limit(10)
            )
            scores = result.scalars().all()
            return [{"username": score.username, "wpm": score.wpm} for score in scores]
    except Exception as e:
        print(f"Error di /leaderboard: {e}")
        return {"error": "Gagal mengambil leaderboard, database mungkin belum di-init."}


@app.websocket("/ws/play/{username}")
async def websocket_play(websocket: WebSocket, username: str):
    """
    Endpoint WebSocket untuk matchmaking.
    """
    await websocket.accept()
    websocket.state.username = username
    
    if not waiting_players:
        waiting_players.append(websocket)
        await websocket.send_json({"status": "waiting", "message": "Mencari lawan... (1/2)"})
        
        try:
            while websocket in waiting_players:
                await websocket.receive_text() # Tunggu pesan (ping/pong)
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
                # Loop untuk logika game
                data = await websocket.receive_json() 
                
                # Kirim data ke lawan
                opponent = active_games.get(websocket)
                if opponent:
                    await opponent.send_json({"type": "progress", "data": data})

        except WebSocketDisconnect:
            print(f"Pemain {username} disconnected dari game.")
            
            # Cari lawan yang terhubung dengan websocket ini
            other_player = active_games.pop(websocket, None) # Jika websocket adalah player2
            if not other_player:
                # Jika tidak ketemu, cari di mana websocket adalah player1
                for p1, p2 in list(active_games.items()): # Gunakan list() untuk iterasi aman
                    if p2 == websocket:
                        other_player = p1
                        break
            
            # Hapus entri sebaliknya dari active_games
            if other_player in active_games:
                active_games.pop(other_player)

            # Beri tahu pemain lain jika mereka masih terhubung
            if other_player:
                try:
                    await other_player.send_json({
                        "status": "opponent_disconnected",
                        "message": f"{username} telah keluar dari permainan."
                    })
                except Exception as e:
                    print(f"Gagal mengirim pesan disconnect: {e}")