import asyncio
from extensions import init_db, get_async_session, engine
from controllers.game_controller import GameController

game_controller = GameController(get_async_session)

async def main():
    print("--- TCP SERVER STARTUP ---")
    await init_db()
    
    host = '0.0.0.0'
    port = 50000
    
    # MENGGUNAKAN ASYNCIO.START_SERVER SESUAI PERMINTAAN
    # Server ini hanya menerima koneksi raw TCP, bukan WebSocket/HTTP
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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer dihentikan.")