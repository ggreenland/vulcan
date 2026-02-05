# Vulcan - Fireplace Control Service

A web service for controlling a Valor fireplace (Alflex B6R-HATV4P WiFi module) over the local network, accessible securely from anywhere via HTTPS.

## Features

- **Web UI**: Mobile-responsive interface for controlling your fireplace
- **Google OAuth**: Secure authentication with email allowlist
- **HTTPS**: Automatic Let's Encrypt certificates via Caddy
- **API Keys** (optional): Generate keys for Home Assistant, scripts, etc.

## Architecture

```
Internet → Router (port 443) → Raspberry Pi (Caddy → FastAPI) → Fireplace (TCP:2000)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.

## Project Structure

```
vulcan/
├── app/                      # FastAPI application
│   ├── main.py               # Routes and app setup
│   ├── config.py             # Environment configuration
│   ├── fireplace.py          # TCP client for fireplace protocol
│   ├── auth.py               # Google OAuth and session management
│   ├── database.py           # SQLite database operations
│   └── templates/
│       └── index.html        # Web UI template
├── static/                   # Frontend assets
│   ├── style.css             # Styles
│   └── app.js                # Client-side JavaScript
├── tests/                    # Test suite (62 tests)
│   ├── test_api.py           # API endpoint tests
│   ├── test_database.py      # Database operation tests
│   └── test_fireplace_protocol.py  # Protocol encoding tests
├── docs/
│   └── ARCHITECTURE.md       # Detailed architecture documentation
├── .env.example              # Example environment variables
├── Caddyfile                 # Caddy reverse proxy configuration
├── fireplace.service         # systemd service file for deployment
├── requirements.txt          # Python dependencies
├── pytest.ini                # Test configuration
└── README.md                 # This file
```

## Requirements

- Raspberry Pi (or any Linux server on the same network as the fireplace)
- Python 3.10+
- Caddy (for HTTPS reverse proxy)
- Domain name (e.g., via DuckDNS)
- Google Cloud project for OAuth

## Quick Start (Raspberry Pi)

### 1. Clone and Install

```bash
git clone https://github.com/ggreenland/vulcan.git
cd vulcan
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
nano .env
```

Required settings:
```bash
# Fireplace connection
FIREPLACE_IP=192.168.0.22
FIREPLACE_PORT=2000

# Google OAuth (from Google Cloud Console)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# Security
SECRET_KEY=run-openssl-rand-hex-32-to-generate
ALLOWED_EMAILS=you@gmail.com

# App URL
BASE_URL=https://yourdomain.duckdns.org
```

### 3. Set Up Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project → APIs & Services → Credentials
3. Create OAuth 2.0 Client ID (Web application)
4. Add redirect URI: `https://yourdomain.duckdns.org/auth/callback`
5. Copy Client ID and Secret to `.env`

### 4. Set Up Caddy (HTTPS)

```bash
# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy

# Configure
sudo cp Caddyfile /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile  # Update domain
sudo systemctl restart caddy
```

### 5. Configure Router

Forward external port 443 → Raspberry Pi IP, port 443

### 6. Run as Service

```bash
# Edit paths in service file
nano fireplace.service

# Install and start
sudo cp fireplace.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable fireplace
sudo systemctl start fireplace
```

### 7. Verify

```bash
# Check service status
sudo systemctl status fireplace

# Check logs
sudo journalctl -u fireplace -f
```

Visit `https://yourdomain.duckdns.org` and sign in with Google.

## Configuration Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FIREPLACE_IP` | Yes | `192.168.0.22` | Fireplace WiFi module IP |
| `FIREPLACE_PORT` | Yes | `2000` | Fireplace TCP port |
| `GOOGLE_CLIENT_ID` | Yes | - | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | - | OAuth client secret |
| `SECRET_KEY` | Yes | - | Session signing key (32+ chars) |
| `ALLOWED_EMAILS` | Yes | - | Comma-separated allowed emails |
| `BASE_URL` | Yes | - | Public URL (e.g., `https://example.com`) |
| `FIREPLACE_CONTROLLER` | No | `real` | `real` for hardware, `simulated` for local testing |
| `DEV_MODE` | No | `false` | Enable `/test/*` endpoints (no auth) |
| `ENABLE_API_KEYS` | No | `false` | Enable API key management |

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/` | - | Web UI |
| GET | `/health` | - | Health check |
| GET | `/auth/login` | - | Start OAuth |
| GET | `/auth/callback` | - | OAuth callback |
| POST | `/auth/logout` | Session | End session |
| GET | `/api/status` | Session | Fireplace status |
| POST | `/api/power/on` | Session | Turn on |
| POST | `/api/power/off` | Session | Turn off |
| POST | `/api/flame/{level}` | Session | Set flame (0-100) |
| POST | `/api/burner2/on` | Session | Enable burner 2 |
| POST | `/api/burner2/off` | Session | Disable burner 2 |

### Optional: API Key Endpoints (ENABLE_API_KEYS=true)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/keys` | Session | List API keys |
| POST | `/api/keys` | Session | Create API key |
| DELETE | `/api/keys/{id}` | Session | Delete API key |

With API keys enabled, all `/api/*` endpoints also accept `X-API-Key` header.

## Development

### Local Testing

```bash
source venv/bin/activate

# Run with simulated fireplace (no hardware needed)
FIREPLACE_CONTROLLER=simulated uvicorn app.main:app --reload --port 8001

# Or with real fireplace and test endpoints enabled
DEV_MODE=true uvicorn app.main:app --reload --port 8000
```

Test endpoints (DEV_MODE only):
- `GET /test/status` - Fireplace status (no auth)
- `POST /test/flame/{level}` - Set flame (no auth)
- `POST /test/burner2/{on|off}` - Control burner2 (no auth)

### Running Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

## Troubleshooting

### Cannot connect to fireplace

```bash
ping 192.168.0.22
nc -zv 192.168.0.22 2000
```

### OAuth callback fails

1. Verify redirect URI matches exactly in Google Console
2. Check `BASE_URL` matches your domain
3. Ensure Caddy has valid certificates: `sudo systemctl status caddy`

### Service won't start

```bash
sudo journalctl -u fireplace -f
```

## Security

- Only emails in `ALLOWED_EMAILS` can sign in
- All traffic encrypted via HTTPS (Caddy + Let's Encrypt)
- Sessions are signed and HTTP-only
- API keys (if enabled) are bcrypt-hashed

## Related Projects

- [alflex-b6r-hatv4p-protocol](https://github.com/ggreenland/alflex-b6r-hatv4p-protocol) - Reverse-engineered protocol documentation for the Alflex B6R-HATV4P WiFi module used in Valor fireplaces

## License

MIT
