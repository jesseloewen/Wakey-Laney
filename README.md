# Wakey Laney

Wakey Laney is a lightweight Flask app for managing devices on your local network, sending Wake-on-LAN packets, and checking device availability with ping.

## Key Features

- Add, edit, and remove saved devices.
- Send Wake-on-LAN packets per device.
- Ping devices using hostname or direct address.
- Optional per-device password protection for edit, wake, and ping actions.
- Signed remember-password cookies for smoother repeat actions.

## Requirements

- Python 3.10+
- Network access to your target devices (same LAN or valid routed broadcast setup)
- `ping` command available on the host OS

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Then open `http://localhost:7448`.

## Configuration

Copy `.env.example` to `.env` and adjust as needed.

| Variable | Default | Purpose |
|---|---|---|
| `APP_HOST` | `0.0.0.0` | Flask bind host |
| `APP_PORT` | `7448` | Flask bind port |
| `CORS_ALLOW_ORIGIN` | `*` | Allowed origin for API CORS |
| `DEVICES_FILE` | `devices.json` | Path to stored device definitions |
| `WOL_PORT` | `9` | UDP port used for Wake-on-LAN |
| `PING_TIMEOUT_MS` | `1200` | Ping timeout in milliseconds |
| `REMEMBER_COOKIE_SECRET` | empty | Secret used to sign remember-password cookies |

## Security Notes

- Device passwords are stored as PBKDF2-HMAC-SHA256 hashes with per-device salts.
- Remember-password tokens are signed, not plain-text passwords.
- For production-like use, set a strong `REMEMBER_COOKIE_SECRET` value.
