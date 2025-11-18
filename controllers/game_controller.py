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

    def __init__(self, session_factory: Callable):
        self.waiting_players: List[WebSocket] = []
        self.waiting_events: Dict[WebSocket, asyncio.Event] = {}
        self.opponents: Dict[WebSocket, WebSocket] = {}
        self.game_states: Dict[WebSocket, GameState] = {}
        self.session_factory = session_factory
        self.text_pool = [
            "The boy's name was Santiago. Dusk was falling as the boy arrived with his herd at an abandoned church. The roof had fallen in long ago, and an enormous sycamore had grown on the spot where the sacristy had once stood.",
            "Every day, millions of Indian women and men perform the invisible work that keeps families, economies, and societies functioning yet this care economy remains largely unaccounted for. Care work encompasses tasks such as cooking, cleaning, washing utensils and clothes, dusting, ironing, and caring for children, the elderly, the ill, and persons with disabilities.",
            "Minecraft is a popular sandbox game that allows players to explore, build, and survive in a blocky, pixelated world. Its open-ended gameplay encourages creativity and experimentation, making it one of the most beloved games worldwide. Players can mine resources, craft tools, and construct intricate structures or explore vast landscapes filled with creatures and secrets. "
        ]
        
        # Set untuk melacak semua koneksi pemain yang aktif untuk broadcast real-time
        self.active_connections: Set[WebSocket] = set()

    async def handle_connection(self, websocket: WebSocket, username: str) -> None:
        # simpan username nya
        websocket.state.username = username
        

        self.active_connections.add(websocket)
        print(f"Koneksi baru: {username}. Total koneksi: {len(self.active_connections)}")

        # jika waiting player nya kosong, 
        # maka panggil _enqueue_player
        try:
            if not self.waiting_players:
                matched = await self._enqueue_player(websocket)
                # jika ga matched, maka return dan ga lanjut ke _game_loop.
                if not matched:
                    return
            else:
                # jika waiting player ada orang nya , 
                # maka ambil player paling awal dan panggil _begin_match
                opponent = self.waiting_players.pop(0)
                await self._begin_match(opponent, websocket)

            await self._game_loop(websocket)
            
        except WebSocketDisconnect:
            await self._handle_disconnect(websocket)
        except Exception as e:
            print(f"Error tak terduga di handle_connection untuk {username}: {e}")
            await self._handle_disconnect(websocket)
        finally:
            # Pastikan koneksi dihapus
            self.active_connections.discard(websocket)
            print(f"Koneksi ditutup: {username}. Sisa koneksi: {len(self.active_connections)}")


    async def _enqueue_player(self, websocket: WebSocket) -> bool:
        # untuk menunggu lawan
        event = asyncio.Event()
        # tambahkan player ke waiting list
        self.waiting_players.append(websocket)
        self.waiting_events[websocket] = event

        # kasih tau player kalau sedang mencari lawan
        await self._safe_send(websocket, {
            "status": "waiting",
            "message": "Mencari lawan... (1/2)"
        })

        # tunggu sampai ada lawan atau player yang disconnect
        matched = await self._wait_for_match_or_disconnect(websocket, event)
        # jika ga matched, maka hapus player dari waiting list
        if not matched:
            await self._cleanup_waiting(websocket)
        return matched

    async def _wait_for_match_or_disconnect(
        # untuk menunggu lawan atau player yang disconnect
        self, websocket: WebSocket, event: asyncio.Event
    ) -> bool:
        disconnect_task = asyncio.create_task(self._watch_disconnect(websocket))
        wait_task = asyncio.create_task(event.wait())

        # tunggu mana yang terjadi dluan, disconnect atau matching nya.
        done, _ = await asyncio.wait(
            {disconnect_task, wait_task},
            return_when=asyncio.FIRST_COMPLETED
        )

        # kalau disconnect dluan, matching di cancel
        if disconnect_task in done and not disconnect_task.cancelled():
            wait_task.cancel()
            await self._cancel_safely(wait_task)
            return False

        # kalau matching dluan, maka matchnya akan menjadi true untuk lanjut main
        disconnect_task.cancel()
        await self._cancel_safely(disconnect_task)
        return True

    async def _watch_disconnect(self, websocket: WebSocket) -> None:
        # cek apakah websocket ada kirim pesan
        # kalau ternyata websocket nya mati, maka akan direturn
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            return

    async def _begin_match(self, player1: WebSocket, player2: WebSocket) -> None:
        # pilih text buat dimainkan
        # menggunakan random
        target_text = random.choice(self.text_pool)

        # status selama game berlangsung
        state = GameState(players=[player1, player2], target_text=target_text)

        self.opponents[player1] = player2
        self.opponents[player2] = player1
        self.game_states[player1] = state
        self.game_states[player2] = state

        # kasih tau player kalu akan bermain
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
            # kasih player countrdown untuk mulai game
            await self._broadcast(state.players, {
                "type": "countdown",
                "value": number
            })
            await asyncio.sleep(1)

        # kasih ke player text yang harus diketik
        state.start_time = asyncio.get_running_loop().time()
        await self._broadcast(state.players, {
            "type": "start_game",
            "text": state.target_text
        })

    async def _game_loop(self, websocket: WebSocket) -> None:
        try:
            while True:
                # tunggu pesan dari pemain
                # biar tau apakah pemain masih bermain atau disconnect
                message = await websocket.receive_json()
                await self._process_game_message(websocket, message)
        except WebSocketDisconnect:
            await self._handle_disconnect(websocket)
        except Exception as e:
            # jika disconnect, game dihentikan dan kasih tau ke lawan
            print(f"Error di game loop {websocket.state.username}: {e}")
            await self._handle_disconnect(websocket)

    async def _process_game_message(self, websocket: WebSocket, message: dict) -> None:
        # cari tau apakah pemain sedang bermain atau sudah finihs
        msg_type = message.get("type")

        # kalau masih progress bermain
        # kasih tau lawan nya berapa progress ketikan musuh
        if msg_type == "progress":
            await self._relay_progress(websocket, message)
            # jika sudah finisih 
            # cek siapa yang menang dan kasih tau ke semua pemain
        elif msg_type == "finish":
            await self._finish_game(websocket, message)
        else:
            print(f"Pesan tidak dikenal: {message}")

    async def _relay_progress(self, websocket: WebSocket, message: dict) -> None:
        opponent = self.opponents.get(websocket)
        if not opponent:
            return

        # data progress pemain
        payload = {
            "type": "opponent_progress",
            "progress": message.get("progress"),
            "wpm": message.get("wpm"),
            "characters": message.get("characters")
        }
        # kasih tau progress ke lawan
        await self._safe_send(opponent, payload)

    async def _finish_game(self, websocket: WebSocket, message: dict) -> None:
        state = self.game_states.get(websocket)
        if not state or state.finished:
            return

        # hitung finish nya
        # dan cari tau siapa yang menang
        opponent = self.opponents.get(websocket)
        now = asyncio.get_running_loop().time()
        elapsed = max(now - (state.start_time or now), 0.1)
        wpm = self._calculate_wpm(len(state.target_text), elapsed)
        state.finished = True
        state.winner = websocket.state.username

        
        # simpan scroe masukkin ke database
        await self._record_score(websocket.state.username, wpm)
        
        # ambil data score baru
        new_leaderboard = await self._get_leaderboard()

        # kasih leaderboard baru ke semua klien yang terhubung
        print(f"Broadcasting leaderboard update ke {len(self.active_connections)} klien.")
        await self._broadcast_leaderboard_update(new_leaderboard)

        # kasih pesan ke yang menang
        await self._safe_send(websocket, {
            "type": "game_over",
            "result": "won",
            "wpm": wpm,
            "text": state.target_text,
            "leaderboard": new_leaderboard 
        })
        
        # kasih pesan ke yang kalah
        if opponent:
            await self._safe_send(opponent, {
                "type": "game_over",
                "result": "lost",
                "wpm": 0, 
                "winner": websocket.state.username,
                "text": state.target_text,
                "leaderboard": new_leaderboard
            })
            #reset status pemain biar nanti bisa masuk ke match yang baru
            await self._cleanup_player(opponent)

        await self._cleanup_player(websocket)

    async def _record_score(self, username: str, wpm: int) -> None:
        try:
            # fungsi untuk simpan score ke database
            async with self.session_factory() as session:
                async with session.begin():
                    session.add(Score(username=username, wpm=wpm))
            print(f"Skor disimpan: {username} - {wpm} WPM")
        except Exception as exc:
            print(f"Gagal menyimpan skor untuk {username}: {exc}")

    async def _broadcast(self, players: List[WebSocket], payload: dict) -> None:
        await asyncio.gather(*(self._safe_send(player, payload) for player in players))

    async def _broadcast_leaderboard_update(self, leaderboard_data: List[dict]):
        # fungsi buat kasih leaderboard ke player pklayer
        payload = {
            "type": "leaderboard_update",
            "leaderboard": leaderboard_data
        }
        await asyncio.gather(
            *(self._safe_send(ws, payload) for ws in self.active_connections)
        )

    async def _safe_send(self, websocket: WebSocket, payload: dict) -> None:
        try:
            # kirim pesan ke satu pemain
            await websocket.send_json(payload)
        except (RuntimeError, WebSocketDisconnect):
            # hapus koneksi jika ada yg diskonect
            self.active_connections.discard(websocket)
        except Exception as exc:
            # error selain diatas
            # error akan dikirim ke server buat kasih tau masalahnya
            print(f"Gagal mengirim pesan ke {getattr(websocket.state, 'username', 'unknown')}: {exc}")
            self.active_connections.discard(websocket)

    async def _handle_disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

        # kasih tau jiak ada yg disconnect
        # lalu hapus status p;ayer jika dia disconnect
        if websocket in self.waiting_players:
            await self._cleanup_waiting(websocket)
            return

        opponent = self.opponents.get(websocket)
        if opponent:
            # lawan nanti akan dikasih pesan jika musuh ny disconnect
            await self._safe_send(opponent, {
                "status": "opponent_disconnected",
                "message": f"{websocket.state.username} telah keluar dari permainan."
            })
            await self._cleanup_player(opponent)

        await self._cleanup_player(websocket)

    async def _cleanup_waiting(self, websocket: WebSocket) -> None:
        # untuk membersihkan player yang disconnet
        # saat sedang matching player
        if websocket in self.waiting_players:
            self.waiting_players.remove(websocket)
        event = self.waiting_events.pop(websocket, None)
        if event:
            event.set()

    async def _cleanup_player(self, websocket: Optional[WebSocket]) -> None:
        # membersihkan data dari pemain pemain
        # ketika pemain sudah selesai bermain
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
        try:
            # ambil data secara async
            async with self.session_factory() as session:
                result = await session.execute(
                    select(Score).order_by(Score.wpm.desc()).limit(10)
                )
                scores = result.scalars().all()
                # ambil data lalu dijadiin dictionary agar mudah di tampilkan
                return [{"username": score.username, "wpm": score.wpm} for score in scores]
        except Exception as exc:
            # kasih tau pesan jika data leaderboard gagal
            print(f"Gagal mengambil leaderboard: {exc}")
            return []