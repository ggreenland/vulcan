# Vulcan - Architecture

## Overview

A web service running on a Raspberry Pi that exposes a secure REST API and web interface to control a Valor fireplace (Alflex B6R-HATV4P WiFi module) from anywhere.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         INTERNET                                │
│                    (Phone, Laptop, etc.)                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    yourdomain.duckdns.org:443                     │
│                         (Your Router)                           │
│                      Port Forward → Pi:443                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RASPBERRY PI                               │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Caddy (Port 443)                                         │  │
│  │  ├─ HTTPS termination (TLS 1.3)                           │  │
│  │  ├─ Automatic Let's Encrypt certificates                  │  │
│  │  ├─ Certificate auto-renewal                              │  │
│  │  └─ Reverse proxy → localhost:8000                        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  FastAPI Application (Port 8000)                          │  │
│  │  ├─ Google OAuth 2.0 authentication                       │  │
│  │  ├─ API key authentication (optional, ENABLE_API_KEYS)    │  │
│  │  ├─ REST API endpoints                                    │  │
│  │  ├─ Web UI (server-rendered HTML)                         │  │
│  │  └─ SQLite database                                       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              │ TCP Port 2000                    │
│                              │ (Local network only)             │
└──────────────────────────────┼──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                 FIREPLACE (192.168.0.22:2000)                   │
│                   Alflex B6R-HATV4P Module                      │
│                                                                 │
│  Protocol: TCP with ASCII hex-encoded commands                  │
│  Frame: STX (0x02) + payload + ETX (0x03)                       │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Caddy (Reverse Proxy)

**Purpose:** Handle HTTPS and certificate management

**Responsibilities:**
- Terminate TLS connections from the internet
- Obtain and renew Let's Encrypt certificates automatically
- Forward decrypted requests to FastAPI on localhost
- Handle HTTP → HTTPS redirects

**Configuration:** Single `Caddyfile`
```
yourdomain.duckdns.org {
    reverse_proxy localhost:8000
}
```

**Why Caddy:**
- Zero-config HTTPS with automatic cert management
- Minimal resource usage on Pi
- Simple configuration vs nginx + certbot

### 2. FastAPI Application

**Purpose:** Core application logic, API, and web interface

**Modules:**

```
app/
├── main.py          # FastAPI app, route definitions, middleware
├── config.py        # Environment configuration (pydantic settings)
├── fireplace.py     # Async TCP client for fireplace protocol
├── auth.py          # Google OAuth flow, API key validation
├── database.py      # SQLite models and async operations
└── templates/
    └── index.html   # Web UI template
```

**Key Design Decisions:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Async framework | FastAPI with asyncio | Non-blocking fireplace TCP calls |
| Template engine | Jinja2 (built into FastAPI) | Server-side rendering, no JS framework needed |
| Database | SQLite with aiosqlite | No separate server, async support, sufficient for single-user |
| Session storage | Signed cookies + DB | Stateless verification, revocable sessions |

### 3. Database Schema

```
┌─────────────────────────────────────────┐
│ users                                   │
├─────────────────────────────────────────┤
│ id          INTEGER PRIMARY KEY         │
│ email       TEXT UNIQUE NOT NULL        │
│ name        TEXT                        │
│ picture     TEXT                        │
│ created_at  TIMESTAMP                   │
│ last_login  TIMESTAMP                   │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ api_keys                                │
├─────────────────────────────────────────┤
│ id          INTEGER PRIMARY KEY         │
│ user_id     INTEGER REFERENCES users    │
│ name        TEXT NOT NULL               │
│ key_hash    TEXT NOT NULL               │
│ prefix      TEXT NOT NULL (first 8 chr) │
│ created_at  TIMESTAMP                   │
│ last_used   TIMESTAMP                   │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ sessions                                │
├─────────────────────────────────────────┤
│ id          TEXT PRIMARY KEY            │
│ user_id     INTEGER REFERENCES users    │
│ created_at  TIMESTAMP                   │
│ expires_at  TIMESTAMP                   │
└─────────────────────────────────────────┘
```

### 4. Fireplace Protocol Client

**Protocol Overview:**
- Transport: TCP on port 2000
- Framing: STX (0x02) + ASCII hex payload + ETX (0x03)
- No authentication (relies on local network isolation)

**Commands:**

| Action | Payload | Notes |
|--------|---------|-------|
| ON | 3-command sequence | 500ms delays between commands |
| OFF | `303030308010` | Network standby mode |
| Flame Level | `303030308016XX` | XX = 0x80 (0%) to 0xFF (100%) |
| Burner2 ON | `30303030802001` | |
| Burner2 OFF | `30303030802000` | |
| Status | `303030308003` | Returns 53-byte device info |

**Status Response Parsing:**
- Byte 7: Power state (0x00=OFF, 0x80-0xFF=ON with flame level)
- Byte 9 bit 3: Burner2 state
- Byte 9 bit 7: Pilot light state
- Bytes 18-33: Device name

## Authentication Flow

### Google OAuth (Web UI)

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Browser │     │  FastAPI │     │  Google  │     │ Database │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │
     │ GET /          │                │                │
     │───────────────>│                │                │
     │                │                │                │
     │  302 → /auth/login              │                │
     │<───────────────│                │                │
     │                │                │                │
     │ GET /auth/login│                │                │
     │───────────────>│                │                │
     │                │                │                │
     │  302 → Google OAuth             │                │
     │<───────────────│                │                │
     │                │                │                │
     │ Google login page               │                │
     │────────────────────────────────>│                │
     │                │                │                │
     │ User authenticates              │                │
     │<────────────────────────────────│                │
     │                │                │                │
     │ GET /auth/callback?code=...     │                │
     │───────────────>│                │                │
     │                │                │                │
     │                │ Exchange code  │                │
     │                │───────────────>│                │
     │                │                │                │
     │                │ Token + user   │                │
     │                │<───────────────│                │
     │                │                │                │
     │                │ Verify email in allowlist       │
     │                │                │                │
     │                │ Create/update user              │
     │                │───────────────────────────────>│
     │                │                │                │
     │                │ Create session │                │
     │                │───────────────────────────────>│
     │                │                │                │
     │ 302 → / (Set-Cookie: session)   │                │
     │<───────────────│                │                │
     │                │                │                │
```

### API Key (Automation)

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Client  │     │  FastAPI │     │ Database │
└────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │
     │ GET /api/status                 │
     │ X-API-Key: sk_abc123...         │
     │───────────────>│                │
     │                │                │
     │                │ Hash key, lookup
     │                │───────────────>│
     │                │                │
     │                │ Key found, valid
     │                │<───────────────│
     │                │                │
     │                │ Update last_used
     │                │───────────────>│
     │                │                │
     │ 200 OK         │                │
     │ {"power": true, ...}            │
     │<───────────────│                │
```

## Security Model

### Layers of Protection

1. **Network Layer**
   - HTTPS encryption (TLS 1.3 via Caddy)
   - Fireplace only accessible on local network

2. **Authentication Layer**
   - Google OAuth with email allowlist
   - API keys hashed with bcrypt

3. **Session Layer**
   - Signed cookies (HMAC)
   - Server-side session validation
   - Configurable expiration

4. **Application Layer**
   - CSRF protection via OAuth state parameter
   - HTTPOnly, Secure, SameSite cookies
   - Input validation on all endpoints

### Threat Considerations

| Threat | Mitigation |
|--------|------------|
| Unauthorized access | Google OAuth + email allowlist |
| Session hijacking | HTTPOnly, Secure cookies, TLS |
| API key theft | Keys shown once, hashed storage |
| Man-in-the-middle | TLS 1.3 via Caddy |
| Fireplace protocol injection | Fireplace on local network only |

## Data Flow

### Control Command (e.g., Set Flame to 50%)

```
Phone Browser
     │
     │ POST /api/flame/50
     │ Cookie: session=...
     ▼
Caddy (HTTPS)
     │
     │ Decrypt TLS
     │ Forward to localhost:8000
     ▼
FastAPI
     │
     ├─ Validate session cookie
     ├─ Check user in database
     ├─ Calculate hex value (0xBF for 50%)
     ├─ Build command: 303030308016BF
     │
     ▼
Fireplace Client (async)
     │
     │ TCP connect to 192.168.0.22:2000
     │ Send: 0x02 + "303030308016BF" + 0x03
     │ Receive: ACK response
     │
     ▼
FastAPI
     │
     │ Return JSON: {"success": true, "flame_level": 50}
     ▼
Phone Browser
     │
     │ Update UI
```

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Raspberry Pi                               │
│                                                                 │
│  ┌─────────────────────┐    ┌─────────────────────────────────┐ │
│  │ systemd             │    │ File System                     │ │
│  │                     │    │                                 │ │
│  │ ┌─────────────────┐ │    │ /home/pi/fireplace-service/     │ │
│  │ │ caddy.service   │ │    │ ├── app/                        │ │
│  │ │ (auto-start)    │ │    │ ├── static/                     │ │
│  │ └─────────────────┘ │    │ ├── .env                        │ │
│  │                     │    │ └── requirements.txt            │ │
│  │ ┌─────────────────┐ │    │                                 │ │
│  │ │ fireplace.svc   │ │    │ /etc/caddy/Caddyfile            │ │
│  │ │ (auto-start)    │ │    │                                 │ │
│  │ └─────────────────┘ │    │ /var/lib/fireplace/             │ │
│  │                     │    │ └── fireplace.db (SQLite)       │ │
│  └─────────────────────┘    └─────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Technology Stack Summary

| Layer | Technology | Version |
|-------|------------|---------|
| OS | Raspberry Pi OS | Latest |
| Python | Python 3 | 3.9+ |
| Web Framework | FastAPI | 0.100+ |
| ASGI Server | Uvicorn | 0.23+ |
| Reverse Proxy | Caddy | 2.x |
| Database | SQLite | 3.x |
| Async DB Driver | aiosqlite | 0.19+ |
| HTTP Client | httpx | 0.24+ |
| OAuth Library | Authlib | 1.2+ |
| Password Hashing | bcrypt | 4.0+ |
