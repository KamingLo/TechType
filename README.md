Typing Race (TCP Socket Implementation)Proyek ini adalah game adu cepat mengetik (typing race) real-time yang dibangun menggunakan Python asyncio dengan komunikasi data berbasis TCP Raw Socket (bukan HTTP/REST API).Proyek ini terdiri dari dua komponen utama:Server (server/): Menjalankan TCP Server murni untuk logika game, matchmaking, dan database.Client (client/): Menjalankan Web Server (AIOHTTP) yang menyajikan antarmuka HTML dan bertindak sebagai bridge (jembatan) antara browser (WebSocket) dan server backend (TCP).Arsitektur SistemsequenceDiagram
    participant Browser as Browser (HTML/JS)
    participant Client as Client.py (Bridge)
    participant Server as Server.py (TCP)
    
    Note over Browser, Client: Protokol WebSocket
    Note over Client, Server: Protokol TCP Raw Socket (JSON Line-based)

    Browser->>Client: Connect WebSocket (/stream/user1)
    Client->>Server: Connect TCP (Port 50000)
    
    Client->>Server: Login Handshake {"type": "login", ...}
    Server-->>Client: Response Leaderboard
    Client-->>Browser: Render Leaderboard
    
    Browser->>Client: Request Match {"type": "req_matchmaking"}
    Client->>Server: Forward TCP
    Server-->>Client: Matched! {"status": "matched"}
    Client-->>Browser: Show Game UI
Mengapa Arsitektur Ini?Low Level Control: Menggunakan TCP stream memungkinkan kontrol penuh atas aliran data tanpa overhead HTTP header.Full Duplex: Komunikasi dua arah yang persisten sangat cocok untuk game real-time.Bridging: Browser tidak bisa melakukan koneksi TCP murni (hanya WebSocket), sehingga client.py bertindak sebagai penerjemah.Struktur DirektoriPastikan struktur folder Anda terlihat seperti ini:proyek_typing/
├── client/
│   ├── templates/
│   │   └── index.html  <-- UI Game (Tailwind CSS)
│   ├── client.py       <-- Web Server & TCP Bridge
│   └── requirements.txt
│
└── server/
    ├── controllers/
    │   └── game_controller.py <-- Logika Inti Game (TCP Handler)
    ├── database/       <-- File .db akan muncul di sini
    ├── models/
    │   └── score.py    <-- Definisi Tabel Database
    ├── extensions.py   <-- Config Database (Async)
    ├── server.py       <-- Entry Point TCP Server
    └── requirements.txt
Cara Instalasi & MenjalankanAnda memerlukan dua terminal terpisah.1. Persiapan Server (Terminal 1)Server akan berjalan di port 50000 (TCP).cd server
# Install dependensi
pip install sqlalchemy aiosqlite

# Jalankan Server
python server.py
Output: Menjalankan TCP Server di 0.0.0.0:500002. Persiapan Client (Terminal 2)Client akan berjalan di port 8000 (HTTP).cd client
# Install dependensi
pip install aiohttp jinja2

# Jalankan Client
python client.py
Output: Menjalankan CLIENT WEB & BRIDGE di http://localhost:80003. BermainBuka browser dan akses: http://localhost:8000Protokol Komunikasi (TCP JSON)Semua pesan dikirim dalam format JSON satu baris, diakhiri dengan karakter newline (\n).Dari Client ke ServerTipe PesanPayload JSONDeskripsiLogin{"type": "login", "username": "Budi"}Dikirim otomatis saat koneksi pertama kali terbentuk.Matchmaking{"type": "req_matchmaking"}Meminta server mencarikan lawan.Progress{"type": "progress", "progress": 50, "wpm": 80}Update status ketikan (real-time).Finish{"type": "finish", "wpm": 100}Memberitahu server bahwa user selesai mengetik.Leaderboard{"type": "req_leaderboard"}Meminta data leaderboard terbaru.Dari Server ke ClientTipe PesanPayload JSONDeskripsiRes Leaderboard{"type": "res_leaderboard", "data": [...]}Data leaderboard (Top 10).Waiting{"status": "waiting", "waiting_count": 1}Sedang menunggu lawan (info jumlah antrian).Matched{"status": "matched", "opponent": "Ani"}Lawan ditemukan.Countdown{"type": "countdown", "value": 3}Hitung mundur (3, 2, 1).Start Game{"type": "start_game", "text": "..."}Game dimulai, teks target dikirim.Opp Progress{"type": "opponent_progress", "progress": 50}Update progress lawan untuk visualisasi bar.Game Over{"type": "game_over", "result": "won/lost"}Hasil akhir game + update leaderboard.Fitur UtamaReal-time Multiplayer: Sinkronisasi progress bar lawan secara instan.Leaderboard Persisten: Data skor disimpan di SQLite dan ditampilkan ulang setiap kali login atau game selesai.Smart Matchmaking:Jika ada pemain menunggu, langsung dipasangkan.Jika tidak, masuk antrian (queue).Menampilkan jumlah orang dalam antrian.Penanganan Disconnect:Jika lawan keluar saat main, game otomatis berhenti dan memberi notifikasi menang/batal.Membersihkan antrian jika pemain menutup browser saat menunggu.