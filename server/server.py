import asyncio
import argparse
import sys
from extensions import init_db, get_async_session
from controllers.game_controller import GameController

# Inisialisasi controller
game_controller = GameController(get_async_session)

async def main(host, port):
    print("\n=== TCP GAME SERVER STARTUP ===")
    
    print("[SERVER] Memeriksa database...")
    await init_db()
    print("[SERVER] Database siap.")
    
    server = await asyncio.start_server(
        game_controller.handle_connection, 
        host, 
        port
    )
    
    print(f"[SERVER] Server berjalan di {host}:{port}")
    print("[SERVER] Menunggu koneksi client...\n")
    
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='TCP Game Server')
    parser.add_argument('--host', action="store", dest="host", required=True, help="Host IP address to bind")
    parser.add_argument('--port', action="store", dest="port", type=int, required=True, help="Port number to bind")
    
    try:
        given_args = parser.parse_args()
        host = given_args.host
        port = given_args.port
        
        asyncio.run(main(host, port))
    except KeyboardInterrupt:
        print("\n[SERVER] Server dihentikan")
    except Exception as e:
        print(f"[ERROR] Fatal: {e}")