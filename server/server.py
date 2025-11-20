import asyncio
import argparse
import sys
from extensions import init_db, get_async_session
from controllers.game_controller import GameController

# Inisialisasi controller
game_controller = GameController(get_async_session)

async def main(host, port):
    print("--- TCP SERVER STARTUP ---")
    
    await init_db()
    
    server = await asyncio.start_server(
        game_controller.handle_connection, 
        host, 
        port
    )
    
    print(f"Menjalankan TCP Server di {host}:{port}")
    print("Menunggu koneksi client...")
    
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
        print("\nServer dihentikan.")
    except Exception as e:
        print(f"Error: {e}")