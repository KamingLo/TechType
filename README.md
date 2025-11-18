# Typing Race – Real-time TCP Socket GameTyping Race adalah game adu cepat mengetik **real-time multiplayer** yang dibangun menggunakan:- Python asyncio  - TCP Raw Socket (bukan HTTP/REST)- AIOHTTP + WebSocket untuk antarmuka browser  - SQLite + SQLAlchemy async sebagai penyimpanan leaderboard  Arsitektur ini memungkinkan kontrol penuh terhadap aliran data, latensi rendah, dan komunikasi dua arah yang stabil.---## 🧠 Arsitektur SistemBrowser → WebSocket (AIOHTTP) → Bridge Client → TCP Raw Socket → Server GameBridge Client berfungsi sebagai translator karena browser tidak bisa melakukan koneksi TCP langsung. Semua protokol komunikasi antar server-client menggunakan JSON dalam satu baris (line-based).---## 📁 Struktur Direktori
```

proyek_typing/
├── client/
    │ ├── templates/│ 
    │ └── index.html│
    ├── client.py│ 
    └── requirements.txt│
└── server/
    ├── controllers/
    │ └── game_controller.py
    ├── database/
    ├── models/
    │ └── score.py
    ├── extensions.py
    ├── server.py
    └──requirements.txt

```
## ⚙️ Cara Instalasi & MenjalankanKamu harus membuka **dua terminal** karena server dan client berjalan terpisah.---### 1. Menjalankan TCP Server (Terminal 1)Port default: **50000**```shcd serverpip install -r requirements.txtpython server.py
```

Output yang muncul:

```
TCP Server running on 0.0.0.0:50000
```

---

### 2. Menjalankan Client Bridge + Web (Terminal 2)

Port default: **8000**

```sh
cd clientpip install -r requirements.txt
python client.py
```

Output:

```
CLIENT WEB running at http://localhost:8000
```

---

### 3. Jalankan di Browser

Buka:

```
http://localhost:8000
```

Game akan otomatis memulai login, menampilkan leaderboard, dan siap matchmaking.

---

## 🔌 Protokol Komunikasi (TCP JSON Line-Based)

Semua paket dikirim dalam satu baris JSON diakhiri `n`.

---

## ➤ Dari Client → Server

### Login

```json
{"type": "login", "username": "Budi"}
```

### Matchmaking

```json
{"type": "req_matchmaking"}
```

### Update Progress

```json
{"type": "progress", "progress": 60, "wpm": 83}
```

### Finish

```json
{"type": "finish", "wpm": 100}
```

### Request Leaderboard

```json
{"type": "req_leaderboard"}
```

---

## ➤ Dari Server → Client

### Leaderboard

```json
{"type": "res_leaderboard", "data": [...]}
```

### Status Waiting

```json
{"status": "waiting", "waiting_count": 1}
```

### Match Found

```json
{"status": "matched", "opponent": "Ani"}
```

### Countdown

```json
{"type": "countdown", "value": 3}
```

### Start Game

```json
{"type": "start_game", "text": "lorem ipsum ..."}
```

### Opponent Progress

```json
{"type": "opponent_progress", "progress": 40}
```

### Game Over

```json
{"type": "game_over", "result": "won"}
```

---

## 🧩 Fitur Utama

-   Multiplayer real-time dua arah berbasis TCP
-   Progress bar sinkron antar pemain
-   Sistem matchmaking otomatis + queue
-   Countdown realtime 3-2-1
-   Leaderboard tersimpan di SQLite
-   Deteksi disconnect lawan
-   Bridge WebSocket ↔ TCP untuk kompatibilitas browser
-   Architecture clean: server fokus logika game, client fokus UI dan jembatan

---

## 🌌 Catatan Pengembangan

Arsitektur ini sangat fleksibel dan bisa dengan mudah dikembangkan menjadi:battle typing, quiz duel, catur real-time, turn-based combat, atau berbagai game sync lainnya karena pondasinya sudah mendukung sinkronisasi low-latency dan event-driven.

---

## 📜 Lisensi

Bebas digunakan untuk belajar maupun proyek pengembangan lanjutan.