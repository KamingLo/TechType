# Library yang digunakan oleh client
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

# Fungsi yang berguna untuk merender template index.html agar dapat ditampilkan ke dalam website
async def handle_index(request):
    return aiohttp_jinja2.render_template('index.html', request, {})

# Fungsi yang dibuat untuk sebagai pengendali komunikasi dua arah dari client ke server, maupun sebaliknya
# Didalamnya ada dua fungsi browser_to_tcp dan tcp_to_browser
# Referensi Kode Python Implementasi AsyncIOClient.py dari mata kuliah Distributed Systems

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

        # Fungsi yang bertujuan untuk mentranslasi data yang diterima dari browser ke dalam server
        async def browser_to_tcp():
            """Membaca dari Browser, kirim ke TCP Server"""
            async for msg in ws_browser:
                if msg.type == WSMsgType.TEXT:

                    try:
                        data = json.loads(msg.data)
                    except:
                        pass
                    
                    if data and data.get("type") == "client_ip":
                        writer.write((json.dumps({
                            "type": "client_ip",
                            "ip": data.get("ip")
                            }) + "\n").encode())
                        await writer.drain()
                        continue

                    if "progress" not in msg.data:
                        print(f"[CLIENT-TCP] >> Sending to Server: {msg.data}")
                    
                    tcp_msg = msg.data + "\n"
                    writer.write(tcp_msg.encode())
                    await writer.drain()
                elif msg.type == WSMsgType.ERROR:
                    print(f'[CLIENT-WEB] ws_browser connection closed with exception {ws_browser.exception()}')

        # Fungsi yang bertujuan untuk mentranslasi data dari server ke dalam browser
        async def tcp_to_browser():
            """Membaca dari TCP Server, kirim ke Browser"""
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

        await asyncio.wait(
            [asyncio.create_task(browser_to_tcp()), 
             asyncio.create_task(tcp_to_browser())],
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

# fungsi untuk menginisialisasi aplikasi pada pertama kali saat client dijalankan
async def init_app():
    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(TEMPLATE_DIR))
    app.router.add_get('/', handle_index)
    app.router.add_get('/stream/{username}', tcp_bridge_handler)
    return app

# fungsi yang memanggil init_app pada saat program dijalankan
def main():
    print(f"--- CONFIGURATION ---")
    print(f"Target TCP Server : {SERVER_TCP_HOST}:{SERVER_TCP_PORT}")
    print(f"Web Client URL    : http://localhost:8000")
    print(f"---------------------")
    web.run_app(init_app(), port=8000)

# fungsi yang mengganti variabel host dan port jikalau diisi.
# bertujuan untuk memberikan ip dan port server agar client tahu server mana yang dituju
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Game Client Bridge')
    parser.add_argument('--host', action="store", dest="host", required=True, help="Target TCP Server Host")
    parser.add_argument('--port', action="store", dest="port", type=int, required=True, help="Target TCP Server Port")
    
    given_args = parser.parse_args()
    
    SERVER_TCP_HOST = given_args.host
    SERVER_TCP_PORT = given_args.port
    
    main()
