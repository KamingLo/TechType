import asyncio
import os
import json
import aiohttp_jinja2
import jinja2
from aiohttp import web, WSMsgType

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

# Konfigurasi ke Server TCP (game_controller.py)
SERVER_TCP_HOST = '127.0.0.1' 
SERVER_TCP_PORT = 50000

async def handle_index(request):
    return aiohttp_jinja2.render_template('index.html', request, {})

async def tcp_bridge_handler(request):
    """
    Jembatan: WebSocket (Browser) <--> TCP Socket (Server)
    Fitur: Login otomatis ke TCP, lalu piping data game/leaderboard.
    """
    username = request.match_info.get('username')
    print(f"[CLIENT] Browser connect: {username}")

    # 1. Terima koneksi WebSocket dari Browser
    ws_browser = web.WebSocketResponse()
    await ws_browser.prepare(request)

    writer = None
    try:
        # 2. Buka koneksi TCP ke Server Backend
        print(f"[CLIENT] Connecting to TCP Server {SERVER_TCP_HOST}:{SERVER_TCP_PORT}...")
        reader, writer = await asyncio.open_connection(SERVER_TCP_HOST, SERVER_TCP_PORT)
        print("[CLIENT] Connected to TCP Server.")

        # 3. HANDSHAKE: Kirim paket login JSON ke TCP server
        # Ini memicu server mengirim balik Leaderboard (res_leaderboard)
        login_payload = json.dumps({"type": "login", "username": username}) + "\n"
        writer.write(login_payload.encode())
        await writer.drain()

        # --- PIPING DATA ---

        # Task A: Browser (WS) -> TCP Server
        async def browser_to_tcp():
            async for msg in ws_browser:
                if msg.type == WSMsgType.TEXT:
                    # Terima JSON dari browser, tambahkan newline (\n), kirim ke TCP
                    # Ini mencakup: req_matchmaking, progress, finish
                    tcp_msg = msg.data + "\n"
                    writer.write(tcp_msg.encode())
                    await writer.drain()
                elif msg.type == WSMsgType.ERROR:
                    print('ws_browser error')

        # Task B: TCP Server -> Browser (WS)
        async def tcp_to_browser():
            while True:
                # Baca baris dari server TCP (res_leaderboard, matched, game_over, dll)
                data = await reader.readline()
                if not data:
                    break
                
                # Decode bytes -> string -> Kirim ke WebSocket browser
                text_data = data.decode().strip()
                if text_data:
                    await ws_browser.send_str(text_data)

        # Jalankan kedua arah komunikasi secara bersamaan
        await asyncio.wait(
            [asyncio.create_task(browser_to_tcp()), 
             asyncio.create_task(tcp_to_browser())],
            return_when=asyncio.FIRST_COMPLETED
        )

    except Exception as e:
        print(f"[CLIENT] Bridge Error: {e}")
    finally:
        print(f"[CLIENT] Closing session for {username}")
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass
        await ws_browser.close()
        return ws_browser

async def init_app():
    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(TEMPLATE_DIR))
    
    app.router.add_get('/', handle_index)
    app.router.add_get('/stream/{username}', tcp_bridge_handler)
    
    return app

def main():
    print("Menjalankan CLIENT WEB & BRIDGE di http://localhost:8000")
    web.run_app(init_app(), port=8000)

if __name__ == '__main__':
    main()