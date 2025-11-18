import asyncio
import json
import random
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

from sqlalchemy.future import select
from sqlalchemy import func 
from models.score import Score

@dataclass
class GameState:
    players: List[asyncio.StreamWriter]
    target_text: str
    start_time: Optional[float] = None
    finished: bool = False
    winner: Optional[str] = None
    metadata: Dict[str, float] = field(default_factory=dict)

class GameController:

    def __init__(self, session_factory: Callable):
        self.waiting_players: List[asyncio.StreamWriter] = []
        self.waiting_events: Dict[asyncio.StreamWriter, asyncio.Event] = {}
        self.opponents: Dict[asyncio.StreamWriter, asyncio.StreamWriter] = {}
        self.game_states: Dict[asyncio.StreamWriter, GameState] = {}
        
        # Mapping writer -> username
        self.player_usernames: Dict[asyncio.StreamWriter, str] = {}
        
        self.session_factory = session_factory
        self.text_pool = [
            "The boy's name was Santiago. Dusk was falling as the boy arrived with his herd at an abandoned church.",
            "Minecraft is a popular sandbox game that allows players to explore, build, and survive in a blocky, pixelated world.",
            "Every day, millions of Indian women and men perform the invisible work that keeps families functioning."
        ]
        self.active_connections: Set[asyncio.StreamWriter] = set()

    async def handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """
        Main loop untuk setiap koneksi TCP client.
        """
        addr = writer.get_extra_info('peername')
        print(f"[SERVER] Koneksi baru dari {addr}")
        username = "Unknown"

        try:
            # 1. FASE HANDSHAKE (LOGIN)
            line = await reader.readline()
            if not line: return

            try:
                login_msg = json.loads(line.decode().strip())
                if login_msg.get('type') == 'login':
                    username = login_msg.get('username')
                    self.player_usernames[writer] = username
                    self.active_connections.add(writer)
                    
                    print(f"[SERVER] User login: {username}")
                    
                    # Kirim leaderboard saat login berhasil
                    lb_data = await self._get_leaderboard()
                    await self._safe_send(writer, {"type": "res_leaderboard", "data": lb_data})
                else:
                    print(f"[SERVER] Handshake gagal: {login_msg}")
                    return
            except json.JSONDecodeError:
                return

            # 2. FASE LOOPING PESAN
            while True:
                line = await reader.readline()
                if not line: break # Koneksi putus
                
                try:
                    message = json.loads(line.decode().strip())
                    await self._process_general_message(writer, message)
                except json.JSONDecodeError:
                    continue

        except Exception as e:
            print(f"[SERVER] Error pada {username}: {e}")
        finally:
            await self._handle_disconnect(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except:
                pass
            print(f"[SERVER] Koneksi {username} ditutup.")

    async def _process_general_message(self, writer: asyncio.StreamWriter, message: dict) -> None:
        msg_type = message.get("type")

        if msg_type == "req_leaderboard":
            leaderboard_data = await self._get_leaderboard()
            await self._safe_send(writer, {
                "type": "res_leaderboard",
                "data": leaderboard_data
            })
        elif msg_type == "req_matchmaking":
            await self._handle_matchmaking_logic(writer)
        elif msg_type in ["progress", "finish"]:
            await self._process_game_play_message(writer, message)

    async def _handle_matchmaking_logic(self, writer: asyncio.StreamWriter):
        # Cek apakah antrian kosong
        if not self.waiting_players:
            matched = await self._enqueue_player(writer)
            if not matched: return
        else:
            # Ambil lawan dari antrian
            while self.waiting_players:
                opponent = self.waiting_players.pop(0)
                # Pastikan koneksi lawan masih aktif
                if not opponent.is_closing():
                    await self._begin_match(opponent, writer)
                    return
            # Jika semua di antrian sudah putus, masuk antrian sendiri
            await self._enqueue_player(writer)

    async def _process_game_play_message(self, writer: asyncio.StreamWriter, message: dict) -> None:
        msg_type = message.get("type")
        if msg_type == "progress":
            await self._relay_progress(writer, message)
        elif msg_type == "finish":
            await self._finish_game(writer, message)

    async def _enqueue_player(self, writer: asyncio.StreamWriter) -> bool:
        event = asyncio.Event()
        self.waiting_players.append(writer)
        self.waiting_events[writer] = event
        
        # Kirim info antrian ke client (termasuk jumlah orang)
        count = len(self.waiting_players)
        await self._safe_send(writer, {
            "status": "waiting", 
            "message": "Menunggu pemain lain...",
            "waiting_count": count
        })
        
        matched = await self._wait_for_match_or_disconnect(writer, event)
        
        if not matched: 
            await self._cleanup_waiting(writer)
            
        return matched

    async def _wait_for_match_or_disconnect(self, writer: asyncio.StreamWriter, event: asyncio.Event) -> bool:
        wait_task = asyncio.create_task(event.wait())
        try:
            await wait_task
            return True
        except asyncio.CancelledError:
            return False

    async def _begin_match(self, player1: asyncio.StreamWriter, player2: asyncio.StreamWriter) -> None:
        target_text = random.choice(self.text_pool)
        state = GameState(players=[player1, player2], target_text=target_text)

        self.opponents[player1] = player2
        self.opponents[player2] = player1
        self.game_states[player1] = state
        self.game_states[player2] = state

        p1_name = self.player_usernames.get(player1, "Unknown")
        p2_name = self.player_usernames.get(player2, "Unknown")

        await self._safe_send(player1, {"status": "matched", "opponent": p2_name})
        await self._safe_send(player2, {"status": "matched", "opponent": p1_name})

        event = self.waiting_events.pop(player1, None)
        if event: event.set()

        await self._run_countdown(state)

    async def _run_countdown(self, state: GameState) -> None:
        for number in (3, 2, 1):
            await self._broadcast(state.players, {"type": "countdown", "value": number})
            await asyncio.sleep(1)
        
        state.start_time = asyncio.get_running_loop().time()
        await self._broadcast(state.players, {"type": "start_game", "text": state.target_text})

    async def _relay_progress(self, writer: asyncio.StreamWriter, message: dict) -> None:
        opponent = self.opponents.get(writer)
        if opponent:
            await self._safe_send(opponent, {
                "type": "opponent_progress", 
                "progress": message.get("progress")
            })

    async def _finish_game(self, writer: asyncio.StreamWriter, message: dict) -> None:
        state = self.game_states.get(writer)
        if not state or state.finished: return
        
        opponent = self.opponents.get(writer)
        username = self.player_usernames.get(writer, "Unknown")
        
        now = asyncio.get_running_loop().time()
        elapsed = max(now - (state.start_time or now), 0.1)
        wpm = self._calculate_wpm(len(state.target_text), elapsed)
        
        state.finished = True
        state.winner = username
        
        # Simpan skor dan ambil leaderboard baru
        await self._record_score(username, wpm)
        new_leaderboard = await self._get_leaderboard()
        
        # Broadcast update leaderboard ke semua orang yang sedang connect
        await self._broadcast_leaderboard_update(new_leaderboard)

        result_msg = {"type": "game_over", "wpm": wpm, "leaderboard": new_leaderboard}
        
        await self._safe_send(writer, {**result_msg, "result": "won"})
        if opponent:
            await self._safe_send(opponent, {**result_msg, "result": "lost", "winner": username})
            await self._cleanup_player(opponent)
            
        await self._cleanup_player(writer)

    async def _record_score(self, username: str, wpm: int) -> None:
        try:
            async with self.session_factory() as session:
                async with session.begin():
                    session.add(Score(username=username, wpm=wpm))
        except Exception as exc:
            print(f"Gagal menyimpan skor: {exc}")

    async def _get_leaderboard(self) -> List[dict]:
        try:
            async with self.session_factory() as session:
                max_wpm = func.max(Score.wpm).label("max_wpm")
                query = (select(Score.username, max_wpm).group_by(Score.username).order_by(max_wpm.desc()).limit(10))
                result = await session.execute(query)
                return [{"username": row.username, "wpm": row.max_wpm} for row in result.all()]
        except Exception as exc:
            print(f"Gagal mengambil leaderboard: {exc}")
            return []

    async def _broadcast_leaderboard_update(self, data: List[dict]):
        payload = {"type": "leaderboard_update", "leaderboard": data}
        active = list(self.active_connections)
        for writer in active:
            await self._safe_send(writer, payload)

    async def _broadcast(self, players: List[asyncio.StreamWriter], payload: dict) -> None:
        for p in players:
            await self._safe_send(p, payload)

    async def _safe_send(self, writer: asyncio.StreamWriter, payload: dict) -> None:
        try:
            if writer.is_closing(): return
            # Protokol TCP: Kirim JSON + Newline
            data = json.dumps(payload) + "\n"
            writer.write(data.encode())
            await writer.drain()
        except Exception:
            pass # Ignore if failed write

    async def _handle_disconnect(self, writer: asyncio.StreamWriter) -> None:
        if writer in self.active_connections:
            self.active_connections.remove(writer)
            
        username = self.player_usernames.pop(writer, "Unknown")
            
        if writer in self.waiting_players:
            await self._cleanup_waiting(writer)
            
        opponent = self.opponents.get(writer)
        if opponent:
            await self._safe_send(opponent, {
                "status": "opponent_disconnected", 
                "message": f"{username} keluar."
            })
            await self._cleanup_player(opponent)
            
        await self._cleanup_player(writer)

    async def _cleanup_waiting(self, writer: asyncio.StreamWriter) -> None:
        if writer in self.waiting_players:
            self.waiting_players.remove(writer)
        event = self.waiting_events.pop(writer, None)
        if event: event.set()

    async def _cleanup_player(self, writer: asyncio.StreamWriter) -> None:
        if not writer: return
        self.opponents.pop(writer, None)
        self.game_states.pop(writer, None)

    def _calculate_wpm(self, text_length: int, elapsed_seconds: float) -> int:
        words = text_length / 5
        minutes = max(elapsed_seconds / 60, 1e-3)
        return max(1, round(words / minutes))