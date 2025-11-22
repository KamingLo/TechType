import asyncio
import os
import json
import argparse
import aiohttp_jinja2
import jinja2
from aiohttp import web, WSMsgType

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

SERVER_TCP_HOST = '127.0.0.1' 
SERVER_TCP_PORT = 50000

async def handle_index(request):
    return aiohttp_jinja2.render_template('index.html', request, {})

async def tcp_bridge_handler(request):
    """
    Jembatan: WebSocket (Browser) <--> TCP Socket (Server)
    """
    username = request.match_info.get('username')
    print(f"[CLIENT-WEB] Browser connected: {username}")

    ws_browser = web.WebSocketResponse()
    await ws_browser.prepare(request)

    writer = None
    try:
        print(f"[CLIENT-TCP] Connecting to {SERVER_TCP_HOST}:{SERVER_TCP_PORT}...")
        reader, writer = await asyncio.open_connection(SERVER_TCP_HOST, SERVER_TCP_PORT)
        print("[CLIENT-TCP] Connected.")

        login_payload = json.dumps({"type": "login", "username": username}) 
        print(f"[CLIENT-TCP] >> Sending Login: {login_payload}")
        writer.write((login_payload + "\n").encode())
        await writer.drain()

        async def browser_to_tcp():
            async for msg in ws_browser:
                if msg.type == WSMsgType.TEXT:
                    if "ping" in msg.data: continue 
                    
                    if "progress" not in msg.data:
                        print(f"[CLIENT-TCP] >> Sending to Server: {msg.data}")
                    
                    tcp_msg = msg.data + "\n"
                    writer.write(tcp_msg.encode())
                    await writer.drain()
                elif msg.type == WSMsgType.ERROR:
                    print(f'[CLIENT-WEB] ws_browser closed with exception {ws_browser.exception()}')

        async def tcp_to_browser():
            while True:
                data = await reader.readline()
                if not data:
                    print("[CLIENT-TCP] Server closed connection.")
                    break
                text_data = data.decode().strip()
                if text_data:
                    if "opponent_progress" not in text_data:
                        print(f"[CLIENT-TCP] << Received from Server: {text_data}")
                    await ws_browser.send_str(text_data)

        async def heartbeat():
            while True:
                await asyncio.sleep(1)
                if not ws_browser.closed:
                    await ws_browser.send_json({"type": "ping"})
                else:
                    break

        await asyncio.wait(
            [
                asyncio.create_task(browser_to_tcp()), 
                asyncio.create_task(tcp_to_browser()),
                asyncio.create_task(heartbeat())
            ],
            return_when=asyncio.FIRST_COMPLETED
        )

    except Exception as e:
        print(f"[CLIENT] Bridge Error: {e}")
    finally:
        print(f"[CLIENT] Disconnecting session for {username}...")
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass
        await ws_browser.close()
        print("[CLIENT] Done.")
        return ws_browser

async def init_app():
    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(TEMPLATE_DIR))
    app.router.add_get('/', handle_index)
    app.router.add_get('/stream/{username}', tcp_bridge_handler)
    return app

def main():
    print(f"--- CONFIGURATION ---")
    print(f"Target TCP Server : {SERVER_TCP_HOST}:{SERVER_TCP_PORT}")
    print(f"Web Client URL    : http://localhost:8000")
    print(f"---------------------")
    web.run_app(init_app(), port=8000)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Game Client Bridge')
    parser.add_argument('--host', action="store", dest="host", required=True, help="Target TCP Server Host")
    parser.add_argument('--port', action="store", dest="port", type=int, required=True, help="Target TCP Server Port")
    
    given_args = parser.parse_args()
    
    SERVER_TCP_HOST = given_args.host
    SERVER_TCP_PORT = given_args.port
    
    main()