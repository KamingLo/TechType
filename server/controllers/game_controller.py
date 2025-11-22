import asyncio
import json
import random
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
    
    progress_map: Dict[asyncio.StreamWriter, float] = field(default_factory=dict)
    wpm_map: Dict[asyncio.StreamWriter, int] = field(default_factory=dict)

class GameController:

    def __init__(self, session_factory: Callable):
        self.game_duration = 90
        self.waiting_players: List[asyncio.StreamWriter] = []
        self.waiting_events: Dict[asyncio.StreamWriter, asyncio.Event] = {}
        self.opponents: Dict[asyncio.StreamWriter, asyncio.StreamWriter] = {}
        self.game_states: Dict[asyncio.StreamWriter, GameState] = {}
        self.player_usernames: Dict[asyncio.StreamWriter, str] = {}
        self.session_factory = session_factory
        self.text_pool = [
            "Sometimes the problem isn't about time. Not everyone picks the right path for themselves on the first try, and that can be pretty harmful. If you find a path that matches your strengths, you'll go really fast and really far. But the truth is, not everyone can figure that out right away.",
            "Animal birds are also necessary for environmental balance. Their numbers are decreasing due to hunting and other reasons. This has added to the mess in the food chain. The balance is disturbed and natural imbalance is encouraged.",
            "Rivers of the Himalayas are perennial, with water usually obtained from melting ice. There is a smooth flow throughout the year. The Himalayas receive heavy rainfall during the monsoon month, causing frequent flooding due to increased water in the rivers.",
            "Summer is the hottest season of the year although children enjoy it a lot due to the long holiday. It is a very interesting andentertaining season for them as they get a chance to go swimming and enjoy the hilly areas and eat ice cream and theirfavourite fruits.",
            "Honey bees are a fascinating and important species that play a crucial role in our ecosystem. These small creatures may seem insignificant but they are responsible for the pollination of a significant portion of the worlds food crops.",
            "Climate change stands as one of the most pressing issues of our time wielding a profound impact on the delicate balance of ecosystems worldwide. One of the most significant consequences of this global phenomenon is its far-reaching effects on biodiversity.",
            "Water is the lifeblood of our planet essential for all living beings. Yet despite its fundamental importance the world faces an impending water crisis of unprecedented scale. The Global Water Crisis encapsulates a myriad of challenges scarcity pollution unequal distribution and inadequate access to safe drinking water.",
            "In recent decades, fossil fuels such as coal, oil, and natural gas have remained the primary sources of energy across the globe. However, growing environmental concerns and the finite nature of these resources have prompted several countries to promote alternative, renewable energy sources like solar.",
            "In true friendship there is skill and determination like that of a best doctor, patience and tenderness like that of a best mother. Every person should try to make such friendship. A scholar believes that if we get a reliable friend, then our life remains safe.",
            "Literature has been considered as the repast of the elite and the educated. Literature most commonly refers to works of the creative imagination. The literary author is assumed to inhabit the legendary ivory tower which is far removed from the practical concerns of everyday life.",
            "Discipline is the invisible framework that supports every long-term ambition, and it grows stronger each time we choose consistent effort over comfortable excuses. People often wait for motivation, imagining a burst of energy that will carry them to success, yet motivation is like weather-pleasant when it appears.",
            "Globalisation has intensified economic and cultural interactions among nations. While some argue that this phenomenon promotes mutual understanding and development, others fear it threatens traditional values and cultural identity. Both perspectives have validity.",
            "Technology has become an inseparable part of our daily lives, influencing the way we work, communicate, learn, and even think. From the moment we wake up and check our smartphones to the time we go to bed scrolling through social media or watching videos online, technology surrounds us in every possible form. ",
            "I believe that history should be made a compulsory course in high school because history serves as a window to the past, enabling students to understand the roots of society, the evolution of cultures, and the forces that have shaped the world we live in today.",
            "Modern communication has transformed dramatically with the rise of digital technology and global connectivity. Every organization now depends on effective collaboration and constant innovation to maintain competitiveness.",
            "Barbados is an island nation in the eastern Caribbean, known for its white sand beaches, coral reefs, and rich cultural traditions. The capital city, Bridgetown, serves as the political, commercial, and cultural heart of the country.",
            "Minecraft is a popular sandbox game that allows players to explore, build, and survive in a blocky, pixelated world. Its open-ended gameplay encourages creativity and experimentation, making it one of the most beloved games worldwide.",
            "The boy's name was Santiago. Dusk was falling as the boy arrived with his herd at an abandoned church. The roof had fallen in long ago, and an enormous sycamore had grown on the spot where the sacristy had once stood.",
            "Artificial Intelligence has rapidly transforming the functioning of the financial market globally. From high-speed algorithm trading to fraud detection and risk management, AI has become the essential part of the market infrastructure.",
            "The real task is to observe the storm within: the urge to upgrade, to compare, to display. That same storm heats both the atmosphere and the psyche. When awareness deepens, manipulation loses its hold. The person who knows his phone works perfectly will not bow to an advertisement promising completion through an upgrade."
        ]
        self.active_connections: Set[asyncio.StreamWriter] = set()

    async def handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        addr = writer.get_extra_info('peername')
        print(f"[SERVER] Koneksi baru masuk dari {addr}...") 
        username = "Unknown"

        try:
            line = await reader.readline()
            if not line: return

            try:
                print(f"[SERVER] << Raw Data Login dari {addr}: {line.decode().strip()}")
                
                login_msg = json.loads(line.decode().strip())
                if login_msg.get('type') == 'login':
                    username = login_msg.get('username')
                    self.player_usernames[writer] = username
                    self.active_connections.add(writer)
                    
                    print(f"[SERVER] {username} has connected.")
                    
                    lb_data = await self._get_leaderboard()
                    await self._safe_send(writer, {"type": "res_leaderboard", "data": lb_data})
                else:
                    return
            except json.JSONDecodeError:
                print(f"[SERVER] Error decode JSON saat login dari {addr}")
                return

            while True:
                line = await reader.readline()
                if not line: break
                try:
                    decoded_line = line.decode().strip()
            
                    if "progress" not in decoded_line: 
                        print(f"[SERVER] << Diterima dari {username}: {decoded_line}")
                    
                    message = json.loads(decoded_line)
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
            except: pass
            print(f"[SERVER] Koneksi {username} ditutup sepenuhnya.")

    async def _process_general_message(self, writer: asyncio.StreamWriter, message: dict) -> None:
        msg_type = message.get("type")

        if msg_type == "req_leaderboard":
            leaderboard_data = await self._get_leaderboard()
            await self._safe_send(writer, {"type": "res_leaderboard", "data": leaderboard_data})
        
        elif msg_type == "req_matchmaking":
            print(f"[SERVER] {self.player_usernames.get(writer)} meminta matchmaking...")


            asyncio.create_task(self._handle_matchmaking_logic(writer))
            
        elif msg_type == "cancel_matchmaking":
            await self._handle_cancel_matchmaking(writer)
            
        elif msg_type in ["progress", "finish"]:
            await self._process_game_play_message(writer, message)

    async def _handle_matchmaking_logic(self, writer: asyncio.StreamWriter):
        if writer in self.waiting_players:
            return 

        if not self.waiting_players:
            matched = await self._enqueue_player(writer)
            if not matched: return
        else:

            while self.waiting_players:
                opponent = self.waiting_players.pop(0)
                
    
                opp_event = self.waiting_events.pop(opponent, None)
                
                if not opponent.is_closing():
                    print(f"[SERVER] Match found! Memulai game...")
                    
        
                    self.opponents[writer] = opponent
                    self.opponents[opponent] = writer
                    
        
                    if opp_event: opp_event.set()
                    
                    await self._begin_match(opponent, writer)
                    return
            

            await self._enqueue_player(writer)

    async def _handle_cancel_matchmaking(self, writer: asyncio.StreamWriter):
        username = self.player_usernames.get(writer)
        
        if writer in self.waiting_players:
            self.waiting_players.remove(writer)
            


            event = self.waiting_events.pop(writer, None)
            if event: 
                event.set()
                
            print(f"[SERVER] {username} membatalkan matchmaking.")
            
        await self._safe_send(writer, {"type": "matchmaking_canceled"})

    async def _process_game_play_message(self, writer: asyncio.StreamWriter, message: dict) -> None:
        msg_type = message.get("type")
        if msg_type == "progress":
            await self._relay_progress(writer, message)
        elif msg_type == "finish":
            print(f"[SERVER] {self.player_usernames.get(writer)} menyelesaikan balapan!")
            await self._finish_game(writer, message)

    async def _enqueue_player(self, writer: asyncio.StreamWriter) -> bool:
        event = asyncio.Event()
        self.waiting_players.append(writer)
        self.waiting_events[writer] = event
        
        count = len(self.waiting_players)
        print(f"[SERVER] {self.player_usernames.get(writer)} masuk antrian. Total antrian: {count}")
        
        await self._safe_send(writer, {
            "status": "waiting", 
            "message": "Menunggu pemain lain...",
            "waiting_count": count
        })
        
        wait_task = asyncio.create_task(event.wait())
        try:

            await wait_task
            



            if writer in self.opponents:
                return True
            else:
    
                return False
                
        except asyncio.CancelledError:
            return False
        finally:
            if not event.is_set():
                self._cleanup_waiting(writer)

    async def _begin_match(self, player1: asyncio.StreamWriter, player2: asyncio.StreamWriter) -> None:
        target_text = random.choice(self.text_pool)
        state = GameState(players=[player1, player2], target_text=target_text)
        
        state.progress_map[player1] = 0
        state.progress_map[player2] = 0

        self.game_states[player1] = state
        self.game_states[player2] = state

        p1_name = self.player_usernames.get(player1, "Unknown")
        p2_name = self.player_usernames.get(player2, "Unknown")

        print(f"[SERVER] Memulai Match: {p1_name} vs {p2_name}")

        await self._safe_send(player1, {"status": "matched", "opponent": p2_name})
        await self._safe_send(player2, {"status": "matched", "opponent": p1_name})

        await self._run_countdown(state)

    async def _run_countdown(self, state: GameState) -> None:
        for number in (3, 2, 1):
            await self._broadcast(state.players, {"type": "countdown", "value": number})
            await asyncio.sleep(1)
        
        state.start_time = asyncio.get_running_loop().time()
        print(f"[SERVER] GO! Game dimulai untuk {len(state.players)} pemain.")
        
        await self._broadcast(state.players, {
            "type": "start_game", 
            "text": state.target_text,
            "duration": self.game_duration
        })
        
        asyncio.create_task(self._monitor_game_duration(state))

    async def _monitor_game_duration(self, state: GameState):
        try:
            await asyncio.sleep(self.game_duration)
            
            if state.finished:
                return

            print("[SERVER] Waktu habis! Menentukan pemenang berdasarkan progress...")
            state.finished = True
            
            p1, p2 = state.players[0], state.players[1]
            prog1 = state.progress_map.get(p1, 0)
            prog2 = state.progress_map.get(p2, 0)
            
            winner_name = None
            if prog1 > prog2:
                winner_name = self.player_usernames.get(p1, "Unknown")
                state.winner = winner_name
            elif prog2 > prog1:
                winner_name = self.player_usernames.get(p2, "Unknown")
                state.winner = winner_name
            
            text_len = len(state.target_text)
            char_p1 = int((prog1 / 100) * text_len)
            char_p2 = int((prog2 / 100) * text_len)
            
            wpm_p1 = self._calculate_wpm(char_p1, self.game_duration)
            wpm_p2 = self._calculate_wpm(char_p2, self.game_duration)
            
            lb_data = await self._get_leaderboard()
            
            await self._safe_send(p1, {
                "type": "game_over",
                "reason": "timeout",
                "result": "won" if winner_name == self.player_usernames.get(p1) else ("lost" if winner_name else "draw"),
                "wpm": wpm_p1,
                "winner": winner_name,
                "leaderboard": lb_data
            })
            
            await self._safe_send(p2, {
                "type": "game_over",
                "reason": "timeout",
                "result": "won" if winner_name == self.player_usernames.get(p2) else ("lost" if winner_name else "draw"),
                "wpm": wpm_p2,
                "winner": winner_name,
                "leaderboard": lb_data
            })

            for p in state.players:
                await self._cleanup_player(p)

        except Exception as e:
            print(f"[SERVER] Timer Error: {e}")

    async def _relay_progress(self, writer: asyncio.StreamWriter, message: dict) -> None:
        state = self.game_states.get(writer)
        if state and not state.finished:
            state.progress_map[writer] = message.get("progress", 0)
            state.wpm_map[writer] = message.get("wpm", 0)

        opponent = self.opponents.get(writer)
        if opponent:
            await self._safe_send(opponent, {
                "type": "opponent_progress", 
                "progress": message.get("progress"),
                "wpm": message.get("wpm", 0) 
            })

    async def _finish_game(self, writer: asyncio.StreamWriter, message: dict) -> None:
        state = self.game_states.get(writer)
        if not state or state.finished: return
        
        opponent = self.opponents.get(writer)
        username = self.player_usernames.get(writer, "Unknown")
        
        now = asyncio.get_running_loop().time()
        race_time = max(now - (state.start_time or now), 0.1)
        
        correct_chars = len(state.target_text)
        winner_wpm = self._calculate_wpm(correct_chars, race_time)
        
        state.finished = True
        state.winner = username
        
        print(f"[SERVER] Menyimpan skor untuk {username} (WPM: {winner_wpm})")
        await self._record_score(username, winner_wpm)
        new_leaderboard = await self._get_leaderboard()
        await self._broadcast_leaderboard_update(new_leaderboard)

        base_msg = {
            "type": "game_over", 
            "reason": "finish", 
            "leaderboard": new_leaderboard
        }
        
        await self._safe_send(writer, {
            **base_msg, 
            "result": "won", 
            "wpm": winner_wpm 
        })
        
        if opponent:
            opp_progress_pct = state.progress_map.get(opponent, 0)
            opp_correct_chars = int((opp_progress_pct / 100) * len(state.target_text))
            opponent_adjusted_wpm = self._calculate_wpm(opp_correct_chars, race_time)
            
            await self._safe_send(opponent, {
                **base_msg, 
                "result": "lost", 
                "winner": username,
                "wpm": opponent_adjusted_wpm 
            })
            await self._cleanup_player(opponent)
            
        await self._cleanup_player(writer)

    async def _record_score(self, username: str, wpm: int) -> None:
        try:
            async with self.session_factory() as session:
                async with session.begin():
                    session.add(Score(username=username, wpm=wpm))
            print(f"[SERVER] Skor DB Updated: {username} - {wpm} WPM")
        except Exception as exc:
            print(f"[SERVER] Gagal menyimpan skor: {exc}")

    async def _get_leaderboard(self) -> List[dict]:
        try:
            async with self.session_factory() as session:
                max_wpm = func.max(Score.wpm).label("max_wpm")
                query = (select(Score.username, max_wpm).group_by(Score.username).order_by(max_wpm.desc()).limit(10))
                result = await session.execute(query)
                return [{"username": row.username, "wpm": row.max_wpm} for row in result.all()]
        except Exception as exc:
            print(f"[SERVER] Error mengambil leaderboard: {exc}")
            return []

    async def _broadcast_leaderboard_update(self, data: List[dict]):
        print(f"[SERVER] Broadcasting Leaderboard Update ke {len(self.active_connections)} user.")
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
            
            username = self.player_usernames.get(writer, "Unknown")
            msg_type = payload.get("type", "unknown")
            if msg_type not in ["opponent_progress", "countdown"]:
                print(f"[SERVER] >> Mengirim ke {username}: {json.dumps(payload)}")

            data = json.dumps(payload) + "\n"
            writer.write(data.encode())
            await writer.drain()
        except Exception as e:
            print(f"[SERVER] Gagal mengirim data ke client: {e}")

    async def _handle_disconnect(self, writer: asyncio.StreamWriter) -> None:
        if writer in self.active_connections:
            self.active_connections.remove(writer)
        username = self.player_usernames.pop(writer, "Unknown")
        print(f"[SERVER] Handling disconnect: {username}")
        
        if writer in self.waiting_players:
            self._cleanup_waiting(writer)
        opponent = self.opponents.get(writer)
        if opponent:
            await self._safe_send(opponent, {"status": "opponent_disconnected", "message": f"{username} keluar."})
            await self._cleanup_player(opponent)
        await self._cleanup_player(writer)

    def _cleanup_waiting(self, writer: asyncio.StreamWriter) -> None:
        if writer in self.waiting_players:
            self.waiting_players.remove(writer)
        event = self.waiting_events.pop(writer, None)
        if event: event.set()

    async def _cleanup_player(self, writer: asyncio.StreamWriter) -> None:
        if not writer: return
        self.opponents.pop(writer, None)
        self.game_states.pop(writer, None)

    def _calculate_wpm(self, correct_chars_count: int, elapsed_seconds: float) -> int:
        words = correct_chars_count / 5
        minutes = max(elapsed_seconds / 60, 1e-4)
        return max(1, round(words / minutes))