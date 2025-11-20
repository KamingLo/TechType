import asyncio
import os
import json
import argparse
import aiohttp_jinja2
import jinja2
from aiohttp import web, WSMsgType

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

# Variabel global untuk target server TCP
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

    ws_browser = web.WebSocketResponse()
    await ws_browser.prepare(request)

    writer = None
    try:
        print(f"[CLIENT] Connecting to TCP Server {SERVER_TCP_HOST}:{SERVER_TCP_PORT}...")
        reader, writer = await asyncio.open_connection(SERVER_TCP_HOST, SERVER_TCP_PORT)
        print("[CLIENT] Connected to TCP Server.")

        login_payload = json.dumps({"type": "login", "username": username}) + "\n"
        writer.write(login_payload.encode())
        await writer.drain()

        async def browser_to_tcp():
            async for msg in ws_browser:
                if msg.type == WSMsgType.TEXT:
                    tcp_msg = msg.data + "\n"
                    writer.write(tcp_msg.encode())
                    await writer.drain()
                elif msg.type == WSMsgType.ERROR:
                    print('ws_browser error')

        async def tcp_to_browser():
            while True:
                data = await reader.readline()
                if not data:
                    break
                text_data = data.decode().strip()
                if text_data:
                    await ws_browser.send_str(text_data)

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
    print(f"Konfigurasi Target TCP Server: {SERVER_TCP_HOST}:{SERVER_TCP_PORT}")
    print("Menjalankan CLIENT WEB & BRIDGE di http://localhost:8000")
    web.run_app(init_app(), port=8000)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Game Client Bridge')
    parser.add_argument('--host', action="store", dest="host", required=True, help="Target TCP Server Host")
    parser.add_argument('--port', action="store", dest="port", type=int, required=True, help="Target TCP Server Port")
    
    given_args = parser.parse_args()
    
    SERVER_TCP_HOST = given_args.host
    SERVER_TCP_PORT = given_args.port
    
    main()