import asyncio
import random
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set
from sqlalchemy.future import select
from models.score import Score
from fastapi import WebSocket, WebSocketDisconnect
from models.score import Score

@dataclass
class GameState:
    players: List[WebSocket]
    target_text: str
    start_time: Optional[float] = None
    finished: bool = False
    winner: Optional[str] = None
    metadata: Dict[str, float] = field(default_factory=dict)

class GameController:
    """
    Mengelola antrian pemain, memulai pertandingan, dan mencatat skor.
    """

    def __init__(self, session_factory: Callable):
        self.waiting_players: List[WebSocket] = []
        self.waiting_events: Dict[WebSocket, asyncio.Event] = {}
        self.opponents: Dict[WebSocket, WebSocket] = {}
        self.game_states: Dict[WebSocket, GameState] = {}
        self.session_factory = session_factory
        self.text_pool = [
            "The boy's name was Santiago. Dusk was falling as the boy arrived with his herd at an abandoned church. The roof had fallen in long ago, and an enormous sycamore had grown on the spot where the sacristy had once stood.",
            "To be, or not to be, that is the question: Whether 'tis nobler in the mind to suffer The slings and arrows of outrageous fortune, Or to take arms against a sea of troubles And by opposing end them.",
            "It was the best of times, it was the worst of times, it was the age of wisdom, it was the age of foolishness, it was the epoch of belief, it was the epoch of incredulity, it was the season of Light, it was the season of Darkness."
        ]
        
        # Set untuk melacak SEMUA koneksi yang aktif untuk broadcast real-time
        self.active_connections: Set[WebSocket] = set()

    async def handle_connection(self, websocket: WebSocket, username: str) -> None:
        websocket.state.username = username
        
        # Tambahkan koneksi ke set pelacak
        self.active_connections.add(websocket)
        print(f"Koneksi baru: {username}. Total koneksi: {len(self.active_connections)}")

        try:
            if not self.waiting_players:
                matched = await self._enqueue_player(websocket)
                if not matched:
                    return
            else:
                opponent = self.waiting_players.pop(0)
                await self._begin_match(opponent, websocket)

            await self._game_loop(websocket)
            
        except WebSocketDisconnect:
            await self._handle_disconnect(websocket)
        except Exception as e:
            print(f"Error tak terduga di handle_connection untuk {username}: {e}")
            await self._handle_disconnect(websocket)
        finally:
            # Pastikan koneksi SELALU dihapus
            self.active_connections.discard(websocket)
            print(f"Koneksi ditutup: {username}. Sisa koneksi: {len(self.active_connections)}")


    async def _enqueue_player(self, websocket: WebSocket) -> bool:
        event = asyncio.Event()
        self.waiting_players.append(websocket)
        self.waiting_events[websocket] = event

        await self._safe_send(websocket, {
            "status": "waiting",
            "message": "Mencari lawan... (1/2)"
        })

        matched = await self._wait_for_match_or_disconnect(websocket, event)
        if not matched:
            await self._cleanup_waiting(websocket)
        return matched

    async def _wait_for_match_or_disconnect(
        self, websocket: WebSocket, event: asyncio.Event
    ) -> bool:
        disconnect_task = asyncio.create_task(self._watch_disconnect(websocket))
        wait_task = asyncio.create_task(event.wait())

        done, _ = await asyncio.wait(
            {disconnect_task, wait_task},
            return_when=asyncio.FIRST_COMPLETED
        )

        if disconnect_task in done and not disconnect_task.cancelled():
            wait_task.cancel()
            await self._cancel_safely(wait_task)
            return False

        disconnect_task.cancel()
        await self._cancel_safely(disconnect_task)
        return True

    async def _watch_disconnect(self, websocket: WebSocket) -> None:
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            return

    async def _begin_match(self, player1: WebSocket, player2: WebSocket) -> None:
        target_text = random.choice(self.text_pool)
        state = GameState(players=[player1, player2], target_text=target_text)

        self.opponents[player1] = player2
        self.opponents[player2] = player1
        self.game_states[player1] = state
        self.game_states[player2] = state

        await self._safe_send(player1, {
            "status": "matched",
            "message": f"Lawan ditemukan: {player2.state.username}!",
            "opponent": player2.state.username
        })
        await self._safe_send(player2, {
            "status": "matched",
            "message": f"Lawan ditemukan: {player1.state.username}!",
            "opponent": player1.state.username
        })

        
        event = self.waiting_events.pop(player1, None)
        if event:
            event.set()

        await self._run_countdown(state)

    async def _run_countdown(self, state: GameState) -> None:
        for number in (3, 2, 1):
            await self._broadcast(state.players, {
                "type": "countdown",
                "value": number
            })
            await asyncio.sleep(1)

        state.start_time = asyncio.get_running_loop().time()
        await self._broadcast(state.players, {
            "type": "start_game",
            "text": state.target_text
        })

    async def _game_loop(self, websocket: WebSocket) -> None:
        try:
            while True:
                message = await websocket.receive_json()
                await self._process_game_message(websocket, message)
        except WebSocketDisconnect:
            await self._handle_disconnect(websocket)
        except Exception as e:
            print(f"Error di game loop {websocket.state.username}: {e}")
            await self._handle_disconnect(websocket)

    async def _process_game_message(self, websocket: WebSocket, message: dict) -> None:
        msg_type = message.get("type")
        if msg_type == "progress":
            await self._relay_progress(websocket, message)
        elif msg_type == "finish":
            await self._finish_game(websocket, message)
        else:
            print(f"Pesan tidak dikenal: {message}")

    async def _relay_progress(self, websocket: WebSocket, message: dict) -> None:
        opponent = self.opponents.get(websocket)
        if not opponent:
            return

        payload = {
            "type": "opponent_progress",
            "progress": message.get("progress"),
            "wpm": message.get("wpm"),
            "characters": message.get("characters")
        }
        await self._safe_send(opponent, payload)

    async def _finish_game(self, websocket: WebSocket, message: dict) -> None:
        state = self.game_states.get(websocket)
        if not state or state.finished:
            return

        opponent = self.opponents.get(websocket)
        now = asyncio.get_running_loop().time()
        elapsed = max(now - (state.start_time or now), 0.1)
        wpm = self._calculate_wpm(len(state.target_text), elapsed)
        state.finished = True
        state.winner = websocket.state.username

        
        # 1. Rekam skor
        await self._record_score(websocket.state.username, wpm)
        
        # 2. Ambil leaderboard baru
        new_leaderboard = await self._get_leaderboard()

        # 3. Broadcast leaderboard baru ke SEMUA klien yang terhubung
        print(f"Broadcasting leaderboard update ke {len(self.active_connections)} klien.")
        await self._broadcast_leaderboard_update(new_leaderboard)

        # 4. Kirim pesan 'game_over' ke pemain yang bertanding
        await self._safe_send(websocket, {
            "type": "game_over",
            "result": "won",
            "wpm": wpm,
            "text": state.target_text,
            "leaderboard": new_leaderboard  # Kirim juga di sini untuk UI 'game_over'
        })

        if opponent:
            await self._safe_send(opponent, {
                "type": "game_over",
                "result": "lost",
                "wpm": 0, # WPM lawan yang kalah mungkin 0 atau yang terakhir dikirim
                "winner": websocket.state.username,
                "text": state.target_text,
                "leaderboard": new_leaderboard
            })
            await self._cleanup_player(opponent)

        await self._cleanup_player(websocket)

    async def _record_score(self, username: str, wpm: int) -> None:
        try:
            async with self.session_factory() as session:
                async with session.begin():
                    session.add(Score(username=username, wpm=wpm))
            print(f"Skor disimpan: {username} - {wpm} WPM")
        except Exception as exc:
            print(f"Gagal menyimpan skor untuk {username}: {exc}")

    async def _broadcast(self, players: List[WebSocket], payload: dict) -> None:
        await asyncio.gather(*(self._safe_send(player, payload) for player in players))

    async def _broadcast_leaderboard_update(self, leaderboard_data: List[dict]):
        """
        Mengirim update leaderboard ke semua klien yang terhubung.
        """
        payload = {
            "type": "leaderboard_update",
            "leaderboard": leaderboard_data
        }
        await asyncio.gather(
            *(self._safe_send(ws, payload) for ws in self.active_connections)
        )

    async def _safe_send(self, websocket: WebSocket, payload: dict) -> None:
        try:
            await websocket.send_json(payload)
        except (RuntimeError, WebSocketDisconnect):
            # Jika koneksi sudah ditutup, hapus dari pelacak
            self.active_connections.discard(websocket)
        except Exception as exc:
            print(f"Gagal mengirim pesan ke {getattr(websocket.state, 'username', 'unknown')}: {exc}")
            self.active_connections.discard(websocket)

    async def _handle_disconnect(self, websocket: WebSocket) -> None:
        # Hapus koneksi dari set pelacak utama
        self.active_connections.discard(websocket)

        if websocket in self.waiting_players:
            await self._cleanup_waiting(websocket)
            return

        opponent = self.opponents.get(websocket)
        if opponent:
            await self._safe_send(opponent, {
                "status": "opponent_disconnected",
                "message": f"{websocket.state.username} telah keluar dari permainan."
            })
            await self._cleanup_player(opponent)

        await self._cleanup_player(websocket)

    async def _cleanup_waiting(self, websocket: WebSocket) -> None:
        if websocket in self.waiting_players:
            self.waiting_players.remove(websocket)
        event = self.waiting_events.pop(websocket, None)
        if event:
            event.set()

    async def _cleanup_player(self, websocket: Optional[WebSocket]) -> None:
        if not websocket:
            return

        self.opponents.pop(websocket, None)
        self.game_states.pop(websocket, None)

    def _calculate_wpm(self, text_length: int, elapsed_seconds: float) -> int:
        words = text_length / 5
        minutes = max(elapsed_seconds / 60, 1e-3)
        return max(1, round(words / minutes))

    async def _cancel_safely(self, task: asyncio.Task) -> None:
        with suppress(asyncio.CancelledError):
            await task
            
    async def _get_leaderboard(self) -> List[dict]:
        """
        Mengambil 10 skor teratas dari database.
        """
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    select(Score).order_by(Score.wpm.desc()).limit(10)
                )
                scores = result.scalars().all()
                return [{"username": score.username, "wpm": score.wpm} for score in scores]
        except Exception as exc:
            print(f"Gagal mengambil leaderboard: {exc}")
            return []