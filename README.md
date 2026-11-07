# 🐾 Budget Care — Telegram Habit-Saving Bot (v1)

> **Budget Care** adalah bot Telegram *deposit-only habit-saving tracker* berdurasi 2 hingga 365 hari yang mengintegrasikan psikologi pembentukan kebiasaan menabung dengan analogi merawat hewan peliharaan virtual (*virtual pet care*). Setiap target tabungan direpresentasikan sebagai seekor hewan peliharaan virtual yang perlu "diberi makan" (*feed*) secara rutin melalui setoran tabungan nyata atau *Free Food* ($0).

---

## 📌 Daftar Isi
1. [Fitur Utama](#-fitur-utama)
2. [Arsitektur & Tech Stack](#-arsitektur--tech-stack)
3. [Struktur Folder & Penjelasan Tiap File](#-struktur-folder--penjelasan-tiap-file)
4. [Konfigurasi Environment (.env)](#-konfigurasi-environment-env)
5. [Instalasi & Setup Awal](#-instalasi--setup-awal)
6. [Cara Menjalankan Project](#-cara-menjalankan-project)
7. [Penjadwalan Cron Database (pg_cron)](#-penjadwalan-cron-database-pg_cron)
8. [Pengujian & Verifikasi (Testing & Linting)](#-pengujian--verifikasi-testing--linting)
9. [Operasional & Analitik](#-operasional--analitik)

---

## ✨ Fitur Utama

- **Virtual Pet Companion**: 8 spesies unik (*Cat, Dog, Rabbit, Bird, Hamster, Turtle, Fox, Panda*) dengan 4 tingkatan suasana hati (*Ecstatic, Happy, Hungry, Starving*) yang bereaksi terhadap konsistensi menabung.
- **Advance First Feeding (Opsi A)**: Setoran tabungan atau *Free Food* ($0) pada hari pembuatan target ($H+0$) langsung mencukupi kebutuhan makan periode pertama tanpa harus menunggu hari berikutnya, dengan cut-off tetap di $H+1$ pukul 23:59.
- **Free Food ($0) Habit Protection**: Opsi bebas biaya untuk hari-hari sulit tanpa uang tunai agar kondisi hewan tetap 100% prima dan kebiasaan tidak putus, namun secara proporsional tercermin pada *Service Quality Score*.
- **Instant Graduation**: Saat akumulasi tabungan mencapai atau melampaui target, status goal langsung lulus (*graduated*), menghasilkan kartu sertifikat kelulusan, dan membatalkan sisa antrean pengingat.
- **24-Hour Undo Window**: Membatalkan setoran terakhir dalam kurun 24 jam dengan perintah `/undo`, termasuk otomatis membuka kembali (*reopen*) status target jika kelulusan sebelumnya dibatalkan.
- **Smart Digest Notifications**: Pengingat outbox per jam yang menggabungkan hingga 8 hewan peliharaan menjadi 1 pesan ringkas (*digest*) dengan tombol inline cepat *Feed* & *Free Food*.
- **Manajemen Lengkap**: Meninjau status target (`/goals`), pengaturan pengingat & ganti zona waktu non-retroaktif (`/settings`), hapus target tunggal (`/delete`), dan penghapusan seluruh data permanen (*Right to be Forgotten*).
- **Hardening & High Resilience**: Deep health check dengan status 503 otomatis saat database tidak aktif, penanganan Telegram 429 Rate Limit instan, pemulihan crash otomatis (*stale claim recovery*), dan perlindungan spam.

---

## 🏗 Arsitektur & Tech Stack

- **Bahasa & Runtime**: Python 3.12+
- **Bot Framework**: [aiogram 3.x](https://docs.aiogram.dev/) (FSM, Filters, Middlewares, Inline Keyboards)
- **Web API**: [FastAPI](https://fastapi.tiangolo.com/) & Uvicorn (ASGI)
- **Database**: PostgreSQL (Supabase) terisolasi di dalam skema khusus `budget_care` dengan Row-Level Security (RLS) aktif
- **ORM & Migrasi**: SQLAlchemy 2.0 (driver `asyncpg` asinkron) & Alembic
- **Pola Transaksi**: Unit of Work (UoW) & Repository Pattern
- **Scheduler**: Supabase `pg_cron` + `pg_net` (trigger `/internal/tick` per menit)
- **Linting & Testing**: `ruff` & `pytest` (Hypothesis property testing, time-machine, pytest-asyncio)

---

## 📂 Struktur Folder & Penjelasan Tiap File

Berikut adalah peta struktur direktori lengkap dari proyek **Budget Care**:

```text
budget-care/
├── .env                              # File kredensial dan konfigurasi lokal (tidak di-commit)
├── alembic.ini                       # Konfigurasi runner migrasi basis data Alembic
├── pyproject.toml                    # Konfigurasi dependensi project, linter ruff, dan pytest
├── README.md                         # Dokumentasi utama proyek
├── AGENTS.md                         # Panduan perilaku AI Coding Agent (simplicity, surgical edits)
│
├── migrations/                       # Skema migrasi database Alembic
│   ├── env.py                        # Bootstrap engine migrasi async SQLAlchemy
│   ├── script.py.mako                # Template migrasi Alembic
│   └── versions/
│       └── 0001_initial.py           # DDL 11 tabel, Enum types, dan Index skema budget_care
│
├── ops/                              # Skrip operasional, cron, dan runbook
│   ├── pg_cron.sql                   # Skrip SQL untuk setup pg_cron & pg_net di Supabase
│   ├── metrics_queries.sql           # Kumpulan SQL query analitik metrik PRD/SDD
│   └── runbook.md                    # Panduan triase insiden untuk tim on-call
│
├── scripts/                          # Utilitas automasi dan pengujian lokal
│   ├── dev_poll.py                   # Runner bot lokal menggunakan long polling Telegram
│   ├── set_commands.py               # Mendaftarkan daftar menu command ke Telegram Bot API
│   ├── set_webhook.py                # Utilitas set / delete Webhook URL Telegram
│   └── tick_loop.py                  # Simulator cron tick lokal per 60 detik
│
├── src/budgetcare/                   # Source code utama aplikasi
│   ├── config.py                     # Manajemen konfigurasi dan environment settings (Pydantic)
│   ├── logging.py                    # Konfigurasi structured logging (JSON stdout)
│   │
│   ├── api/                          # Modul Web API FastAPI
│   │   ├── app.py                    # Inisialisasi FastAPI application & registrasi router
│   │   └── routes/
│   │       ├── health.py             # Endpoint /health (shallow) dan /health?deep=1 (database check)
│   │       ├── telegram.py           # Endpoint POST /webhook/telegram (webhook handler)
│   │       └── tick.py               # Endpoint POST /internal/tick (cron runner internal)
│   │
│   ├── bot/                          # Antarmuka Telegram Bot (Aiogram 3.x)
│   │   ├── callbacks.py              # Definisi & serializer compact CallbackData inline (<64 bytes)
│   │   ├── copy.py                   # Seluruh teks antarmuka bot (varian 'pet' dan 'plain')
│   │   ├── dispatcher.py             # Builder bot & Aiogram Dispatcher beserta registrasi router
│   │   ├── keyboards.py              # Generator keyboard interaktif inline & reply keyboard
│   │   ├── middleware.py             # UnitOfWorkMiddleware (deduplikasi update & isolasi DB)
│   │   └── routers/                  # Modul routing perintah dan percakapan bot
│   │       ├── common.py             # Handler /cancel, /help, dan fallback pesan tak dikenal
│   │       ├── delete.py             # Handler alur penghapusan target (/delete)
│   │       ├── feed.py               # Handler /feed, tombol free food, dan shortcut angka polos
│   │       ├── goals.py              # Handler daftar target tabungan & detail kartu pet (/goals)
│   │       ├── newgoal.py            # FSM Wizard interaktif pembuatan target baru (/newgoal)
│   │       ├── settings.py           # Handler menu preferensi, notifikasi, timezone, & wipe (/settings)
│   │       ├── start.py              # Handler registrasi pengguna baru & GPS timezone (/start)
│   │       └── undo.py               # Handler pembatalan setoran tabungan 24 jam (/undo)
│   │
│   ├── db/                           # Layer basis data (PostgreSQL)
│   │   ├── engine.py                 # Async engine & connection pooler setup
│   │   ├── tables.py                 # Definisi SQLAlchemy ORM model untuk 11 tabel
│   │   ├── uow.py                    # Implementasi Unit of Work pattern (asynchronous)
│   │   └── repos/                    # Repository per tabel untuk isolasi query SQL
│   │       ├── conversations.py      # Repository status FSM wizard
│   │       ├── entries.py            # Repository ledger setoran uang & free food
│   │       ├── events.py             # Repository log audit dan event analitik
│   │       ├── goals.py              # Repository target tabungan
│   │       ├── locks.py              # Repository distributed lease lock cron
│   │       ├── notifications.py      # Repository outbox pesan pengingat
│   │       ├── periods.py            # Repository jadwal periode tabungan
│   │       ├── tick_runs.py          # Repository riwayat audit eksekusi tick
│   │       ├── updates.py            # Repository deduplikasi update_id Telegram
│   │       └── users.py              # Repository profil pengguna dan zona waktu
│   │
│   ├── domain/                       # Pure Domain Logic & Domain Models (bebas dependensi eksternal)
│   │   ├── models.py                 # Enums & Dataclasses (GoalFrequency, MoodTier, PeriodStatus)
│   │   ├── money.py                  # Helper konversi & formatting integer cents ($/IDR)
│   │   ├── notifications.py          # Logika kalkulasi waktu notifikasi reminder & follow-up
│   │   ├── parsing.py                # Parser input angka, tanda mata uang, dan nominal
│   │   ├── pets.py                   # Katalog spesies pet, emoji, dan mapping mood tier
│   │   ├── schedule.py               # Algoritma perencanaan jadwal cut-off tabungan
│   │   ├── scoring.py                # Algoritma perhitungan Condition %, Live Quality %, & Hasil Akhir
│   │   └── timeutil.py               # Utilitas manipulasi zona waktu IANA & batas midnight 23:59
│   │
│   └── services/                     # Application Services (Orkestrasi Domain + Database UoW)
│       ├── feeding.py                # Orkestrasi setoran, free food, evaluasi Option A, & kelulusan
│       ├── goals.py                  # Orkestrasi pembuatan target atomik dari wizard
│       ├── settings.py               # Orkestrasi ganti timezone, toggle reminder, delete, & wipe
│       ├── tick.py                   # Core engine penutupan periode otomatis & pengiriman digest
│       ├── undo.py                   # Orkestrasi pembatalan transaksi 24 jam & reopening goal
│       └── users.py                  # Registrasi pengguna baru & deteksi zona waktu otomatis
│
└── tests/                            # Test Suite Lengkap
    ├── conftest.py                   # Fixture pengujian pytest & async engine
    ├── integration/                  # Pengujian integrasi terhadap Supabase Postgres nyata
    │   ├── test_m3_wizard.py         # Test alur onboarding & wizard pembuatan target
    │   ├── test_m4_feeding.py        # Test alur feeding, kelulusan seketika, dan undo
    │   ├── test_m5_tick.py           # Test engine tick, penutupan periode, & lease locking
    │   └── test_m6_management.py     # Test penghapusan target, perubahan zona waktu, & wipe data
    └── unit/                         # Pengujian unit domain, service mock, failure drills, & soak
        ├── test_bot_newgoal_filter.py # Test filter wizard agar shortcut angka tidak tertelan
        ├── test_db_models.py         # Test metadata tabel & inisialisasi UoW
        ├── test_failure_drills.py    # Test simulasi 429 rate limit, 403 blocked, & crash recovery
        ├── test_feeding_service.py   # Test logika Option A, free food ganda, & klasifikasi
        ├── test_health.py            # Test endpoint /health & verifikasi deep 503 saat DB putus
        ├── test_money.py             # Test parsing & formatting integer cents
        ├── test_notifications.py     # Test algoritma perencanaan waktu pengingat
        ├── test_parsing.py           # Test parsing nominal uang input pengguna
        ├── test_properties.py        # Property-based testing (Hypothesis) untuk schedule & mood
        ├── test_schedule.py          # Test jadwal tabungan harian, mingguan, & bulanan
        ├── test_scoring.py           # Test skor kondisi, mood tier, & service quality
        ├── test_settings_service.py  # Test unit layanan manajemen preferensi user
        ├── test_tick_api.py          # Test autentikasi rahasia endpoint internal tick
        ├── test_tick_service.py      # Test unit logika penutupan periode tick
        ├── test_tick_soak.py         # Test beban tinggi (500 goals & 300 notifikasi digest)
        ├── test_timeutil.py          # Test konversi zona waktu & cut-off midnight
        └── test_undo_service.py      # Test pembatalan entri sebelum & sesudah batas 24 jam
```

---

## ⚙️ Konfigurasi Environment (`.env`)

Buat file `.env` di direktori utama project dengan menyalin parameter berikut:

```env
# 1. Kredensial Bot Telegram
TELEGRAM_BOT_TOKEN="your_telegram_bot_token_from_botfather"
TELEGRAM_WEBHOOK_SECRET="bc_sec_webhook_random_token_123"

# 2. Secret untuk Cron Internal Tick
TICK_SECRET="bc_sec_tick_random_secret_456"

# 3. Koneksi Supabase Postgres
# DATABASE_URL: Menggunakan Transaction Pooler (port 6543)
DATABASE_URL="postgresql+asyncpg://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres"

# DATABASE_URL_MIGRATIONS: Menggunakan Session Pooler (port 5432) atau Direct Connection untuk Alembic
DATABASE_URL_MIGRATIONS="postgresql+asyncpg://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres"

# 4. App & Storage
APP_ENV="local"
LOG_LEVEL="INFO"
PET_IMAGE_BASE_URL="https://[PROJECT-REF].supabase.co/storage/v1/object/public/pets"

# 5. Parameter Waktu & Pengiriman Notifikasi
CUTOFF_GRACE_SECONDS=60
TICK_TIME_BUDGET_SECONDS=25
TICK_LEASE_SECONDS=120
SEND_RATE_PER_SECOND=25
SEND_BATCH_SIZE=200
```

---

## 🚀 Instalasi & Setup Awal

### 1. Buat & Aktifkan Virtual Environment
```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependensi
```powershell
pip install -e ".[dev]"
```

### 3. Jalankan Migrasi Database
Pastikan database Supabase sudah dibuat dan `DATABASE_URL_MIGRATIONS` telah terisi di `.env`.
```powershell
alembic upgrade head
```
*Perintah ini akan membuat skema `budget_care` beserta 11 tabel pendukungnya.*

### 4. Daftarkan Menu Command Bot Telegram
```powershell
python scripts/set_commands.py
```
*Perintah ini akan mendaftarkan shortcut perintah (`/newgoal`, `/feed`, `/goals`, `/undo`, `/settings`, `/delete`, `/cancel`, `/help`) ke menu Telegram pengguna.*

---

## 🎮 Cara Menjalankan Project

### Opsi A: Mode Pengembangan Lokal (Long Polling)
Cara termudah menjalankan bot di komputer lokal tanpa memerlukan IP publik atau domain webhook:
```powershell
python scripts/dev_poll.py
```
Bot akan otomatis terhubung ke Telegram dan siap menerima interaksi di ruang obrolan Telegram.

### Opsi B: Simulator Otomasi Cron Tick Lokal
Untuk menguji penutupan periode tabungan dan pengiriman notifikasi pengingat secara otomatis setiap 60 detik di mesin lokal:
```powershell
python scripts/tick_loop.py
```

### Opsi C: Menjalankan Server Webhook (FastAPI / Production / Vercel)
Untuk menjalankan web server ASGI lokal:
```powershell
uvicorn budgetcare.api.app:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

Jika server sudah memiliki URL publik (misal: Vercel / ngrok), daftarkan webhook ke Telegram:
```powershell
python scripts/set_webhook.py https://your-domain.vercel.app/webhook/telegram
```

Untuk menghapus webhook (jika ingin kembali ke long polling):
```powershell
python scripts/set_webhook.py delete --drop-pending
```

---

## ⏰ Penjadwalan Cron Database (`pg_cron`)

Untuk lingkungan serverless (Vercel), bot tidak berjalan terus-menerus. Penjadwalan tick per menit didelegasikan ke ekstensi `pg_cron` dan `pg_net` di dalam basis data Supabase:

1. Buka **SQL Editor** pada Supabase Dashboard Anda.
2. Buka file [`ops/pg_cron.sql`](file:///ops/pg_cron.sql).
3. Sesuaikan URL endpoint publik Anda dan rahasia `TICK_SECRET`:
   ```sql
   select vault.create_secret('https://your-domain.vercel.app/internal/tick', 'tick_endpoint');
   select vault.create_secret('your_tick_secret_key', 'tick_secret');
   ```
4. Jalankan script tersebut di Supabase. Job cron akan otomatis memicu `POST /internal/tick` setiap menit (`* * * * *`).

---

## 🧪 Pengujian & Verifikasi (Testing & Linting)

### Menjalankan Test Suite (Pytest)
Project ini dilengkapi dengan **60 skenario pengujian komprehensif** (unit tests, property-based tests, failure drills, soak tests, dan database integration tests):
```powershell
.\.venv\Scripts\pytest -v
```

### Menjalankan Linter & Format Checker (Ruff)
```powershell
.\.venv\Scripts\ruff check .
```

---

## 📊 Operasional & Analitik

- **Operational Runbook**: Lihat [`ops/runbook.md`](file:///ops/runbook.md) untuk panduan triase ketika terjadi kendala operasional (pengingat macet, penanganan Telegram 429, rollback deploy, dsb).
- **Analitik SQL**: Lihat [`ops/metrics_queries.sql`](file:///ops/metrics_queries.sql) untuk mengevaluasi metrik produk utama:
  - *On-Time Feeding Rate*
  - *Day-7 & Day-21 Retention*
  - *Free-Food Usage Ratio*
  - *Bot Block Rate*
  - *Acted-on Reminder Rate (< 2 Jam)*
  - *Pet vs Plain Experiment Comparison*
