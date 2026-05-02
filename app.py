import json
import os
import shutil
import socket
import subprocess
import threading
import time
import uuid
import base64
import hashlib
import hmac
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request


load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"), override=False)

app = Flask(__name__)

DEFAULT_BROADCAST_IP = "192.168.0.255"
DEFAULT_WOL_PORT = 9
DEFAULT_PING_TIMEOUT_MS = 1200
DEVICE_FILE_LOCK = threading.Lock()
PASSWORD_ATTEMPT_LOCK = threading.Lock()

PASSWORD_MIN_LENGTH = 6
PASSWORD_MAX_LENGTH = 128
PASSWORD_PBKDF2_ITERATIONS = 310_000
PASSWORD_ATTEMPT_WINDOW_SECONDS = 60
PASSWORD_ATTEMPT_MAX_FAILURES = 6
PASSWORD_ATTEMPT_LOCKOUT_SECONDS = 120
FAILED_PASSWORD_ATTEMPTS: dict[str, dict] = {}
REMEMBER_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365
REMEMBER_COOKIE_PREFIX = "wakeylaneyrm"
REMEMBER_COOKIE_VERSION = "v1"



def parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def get_env_config() -> dict:
    return {
        "host": os.getenv("APP_HOST", "0.0.0.0").strip() or "0.0.0.0",
        "app_port": parse_int_env("APP_PORT", 7448),
        "cors_allow_origin": os.getenv("CORS_ALLOW_ORIGIN", "*").strip() or "*",
    "remember_cookie_secret": os.getenv("REMEMBER_COOKIE_SECRET", "").strip(),
        "devices_file": os.getenv("DEVICES_FILE", "devices.json").strip() or "devices.json",
        "wol_port": parse_int_env("WOL_PORT", DEFAULT_WOL_PORT),
        "ping_timeout_ms": parse_int_env("PING_TIMEOUT_MS", DEFAULT_PING_TIMEOUT_MS),
    }


def get_devices_file_path(config: dict) -> Path:
    configured_path = Path(config["devices_file"]).expanduser()
    if configured_path.is_absolute():
        return configured_path
    return Path(__file__).resolve().parent / configured_path


def ensure_device_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("[]\n", encoding="utf-8")


def normalize_mac_address(value: str) -> str:
    normalized = value.replace("-", "").replace(":", "").replace(".", "").strip()
    if len(normalized) != 12:
        raise ValueError("MAC address must contain 12 hex characters.")

    try:
        mac_bytes = bytes.fromhex(normalized)
    except ValueError as err:
        raise ValueError("MAC address contains invalid hex characters.") from err

    return ":".join(f"{byte:02X}" for byte in mac_bytes)


def validate_ipv4(value: str, field_name: str) -> str:
    try:
        socket.inet_aton(value)
    except OSError as err:
        raise ValueError(f"{field_name} must be a valid IPv4 address.") from err

    if value.count(".") != 3:
        raise ValueError(f"{field_name} must be a valid IPv4 address.")

    return value


def parse_bool(value, default: bool = False) -> bool:
  if isinstance(value, bool):
    return value
  if isinstance(value, str):
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
      return True
    if lowered in {"0", "false", "no", "off"}:
      return False
  if isinstance(value, (int, float)):
    return bool(value)
  return default


def sanitize_new_password(raw_password: str) -> str:
  password = raw_password.strip()
  if not password:
    raise ValueError("Password cannot be empty.")
  if len(password) < PASSWORD_MIN_LENGTH:
    raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
  if len(password) > PASSWORD_MAX_LENGTH:
    raise ValueError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters.")
  return password


def hash_password(password: str) -> tuple[str, str, int]:
  salt = os.urandom(16)
  digest = hashlib.pbkdf2_hmac(
    "sha256",
    password.encode("utf-8"),
    salt,
    PASSWORD_PBKDF2_ITERATIONS,
  )
  return (
    base64.b64encode(salt).decode("ascii"),
    base64.b64encode(digest).decode("ascii"),
    PASSWORD_PBKDF2_ITERATIONS,
  )


def device_has_password(device: dict) -> bool:
  return bool(
    str(device.get("password_salt", "")).strip()
    and str(device.get("password_hash", "")).strip()
    and int(device.get("password_iterations", 0) or 0) > 0
  )


def verify_device_password(device: dict, candidate: str) -> bool:
  if not device_has_password(device):
    return False

  try:
    salt = base64.b64decode(str(device.get("password_salt", "")), validate=True)
    expected = base64.b64decode(str(device.get("password_hash", "")), validate=True)
    iterations = int(device.get("password_iterations", 0))
  except (ValueError, TypeError):
    return False

  if not candidate or iterations <= 0:
    return False

  actual = hashlib.pbkdf2_hmac(
    "sha256",
    candidate.encode("utf-8"),
    salt,
    iterations,
  )
  return hmac.compare_digest(actual, expected)


def make_password_attempt_key(device_id: str) -> str:
  remote_addr = (request.remote_addr or "unknown").strip() or "unknown"
  return f"{remote_addr}:{device_id}"


def check_password_lockout(device_id: str) -> str | None:
  key = make_password_attempt_key(device_id)
  now = time.monotonic()
  with PASSWORD_ATTEMPT_LOCK:
    state = FAILED_PASSWORD_ATTEMPTS.get(key)
    if not state:
      return None

    lock_until = float(state.get("lock_until", 0.0) or 0.0)
    if lock_until > now:
      seconds_left = int(lock_until - now + 0.999)
      return f"Too many failed password attempts. Try again in {seconds_left}s."

    failures = [t for t in state.get("failures", []) if now - t <= PASSWORD_ATTEMPT_WINDOW_SECONDS]
    if failures:
      FAILED_PASSWORD_ATTEMPTS[key] = {"failures": failures, "lock_until": 0.0}
    else:
      FAILED_PASSWORD_ATTEMPTS.pop(key, None)

  return None


def register_password_failure(device_id: str) -> str:
  key = make_password_attempt_key(device_id)
  now = time.monotonic()
  with PASSWORD_ATTEMPT_LOCK:
    state = FAILED_PASSWORD_ATTEMPTS.get(key, {"failures": [], "lock_until": 0.0})
    failures = [t for t in state.get("failures", []) if now - t <= PASSWORD_ATTEMPT_WINDOW_SECONDS]
    failures.append(now)

    if len(failures) >= PASSWORD_ATTEMPT_MAX_FAILURES:
      lock_until = now + PASSWORD_ATTEMPT_LOCKOUT_SECONDS
      FAILED_PASSWORD_ATTEMPTS[key] = {"failures": failures, "lock_until": lock_until}
      return (
        "Too many failed password attempts. "
        f"Action locked for {PASSWORD_ATTEMPT_LOCKOUT_SECONDS}s."
      )

    FAILED_PASSWORD_ATTEMPTS[key] = {"failures": failures, "lock_until": 0.0}

  return "Invalid password."


def clear_password_failures(device_id: str) -> None:
  key = make_password_attempt_key(device_id)
  with PASSWORD_ATTEMPT_LOCK:
    FAILED_PASSWORD_ATTEMPTS.pop(key, None)


def get_remember_cookie_secret(config: dict) -> str:
  configured_secret = str(config.get("remember_cookie_secret", "")).strip()
  if configured_secret:
    return configured_secret
  return f"wakey-laney-local-secret::{Path(__file__).resolve()}"


def get_remember_cookie_name(device_id: str, app_port: int) -> str:
  safe_device_id = "".join(ch for ch in str(device_id) if ch.isalnum()) or "device"
  return f"{REMEMBER_COOKIE_PREFIX}_{app_port}_{safe_device_id}"


def make_remember_cookie_token(device: dict, config: dict) -> str:
  payload = "|".join(
    [
      REMEMBER_COOKIE_VERSION,
      str(device.get("id", "")),
      str(device.get("password_salt", "")),
      str(device.get("password_hash", "")),
      str(int(device.get("password_iterations", 0) or 0)),
    ]
  )
  secret = get_remember_cookie_secret(config).encode("utf-8")
  signature = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).digest()
  encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
  return f"{REMEMBER_COOKIE_VERSION}.{encoded_signature}"


def has_valid_remember_cookie(device: dict, config: dict) -> bool:
  if not device_has_password(device):
    return False

  cookie_name = get_remember_cookie_name(str(device.get("id", "")), int(config.get("app_port", 0) or 0))
  token = str(request.cookies.get(cookie_name, "")).strip()
  if not token:
    return False

  expected_token = make_remember_cookie_token(device, config)
  return hmac.compare_digest(token, expected_token)


def set_remember_cookie(response, device: dict, config: dict) -> None:
  if not device_has_password(device):
    return

  cookie_name = get_remember_cookie_name(str(device.get("id", "")), int(config.get("app_port", 0) or 0))
  token = make_remember_cookie_token(device, config)
  response.set_cookie(
    cookie_name,
    token,
    max_age=REMEMBER_COOKIE_MAX_AGE_SECONDS,
    httponly=True,
    samesite="Lax",
    secure=bool(request.is_secure),
    path="/",
  )


def clear_remember_cookie(response, device_id: str, config: dict) -> None:
  cookie_name = get_remember_cookie_name(device_id, int(config.get("app_port", 0) or 0))
  response.delete_cookie(cookie_name, path="/")


def require_device_password(device: dict, payload: dict, config: dict) -> tuple[str | None, bool]:
  if not device_has_password(device):
    return None, False

  lockout_error = check_password_lockout(device.get("id", ""))
  if lockout_error:
    return lockout_error, False

  candidate = str(payload.get("password", ""))
  if not candidate:
    if has_valid_remember_cookie(device, config):
      clear_password_failures(device.get("id", ""))
      return None, False
    return "Password is required for this device.", False

  if not verify_device_password(device, candidate):
    return register_password_failure(device.get("id", "")), False

  clear_password_failures(device.get("id", ""))
  return None, True


def require_explicit_current_password(device: dict, payload: dict) -> str | None:
  if not device_has_password(device):
    return None

  lockout_error = check_password_lockout(device.get("id", ""))
  if lockout_error:
    return lockout_error

  current_password = str(payload.get("current_password", ""))
  if not current_password:
    return "Current password is required for this action."

  if not verify_device_password(device, current_password):
    return register_password_failure(device.get("id", ""))

  clear_password_failures(device.get("id", ""))
  return None


def password_error_status(error_message: str) -> int:
  if error_message.startswith("Too many failed"):
    return 429
  if error_message.startswith("Password is required") or error_message.startswith("Current password is required"):
    return 401
  return 403


def build_public_device(device: dict) -> dict:
  has_password = device_has_password(device)
  address = str(device.get("address", "")).strip()
  has_direct_address = bool(address)
  lock_wake_with_password = bool(device.get("lock_wake_with_password", False))
  lock_ping_with_password = bool(device.get("lock_ping_with_password", False))
  lock_wake_ping_with_password = bool(lock_wake_with_password and lock_ping_with_password)
  return {
    "id": device["id"],
    "name": device["name"],
    "mac_address": "" if has_password else device["mac_address"],
    "broadcast_ip": "" if has_password else device["broadcast_ip"],
    "address": "" if has_password else address,
    "has_direct_address": has_direct_address,
    "has_password": has_password,
    "lock_wake_with_password": lock_wake_with_password,
    "lock_ping_with_password": lock_ping_with_password,
    "lock_wake_ping_with_password": lock_wake_ping_with_password,
  }


def build_edit_device(device: dict) -> dict:
  editable = build_public_device(device)
  editable["mac_address"] = device["mac_address"]
  editable["broadcast_ip"] = device["broadcast_ip"]
  editable["address"] = device["address"]
  return editable


def sanitize_loaded_device(entry: dict) -> dict:
    device_id = str(entry.get("id", "")).strip() or uuid.uuid4().hex
    name = str(entry.get("name", "")).strip()
    mac_address = normalize_mac_address(str(entry.get("mac_address", "")).strip())
    broadcast_ip = str(entry.get("broadcast_ip", "")).strip() or DEFAULT_BROADCAST_IP
    broadcast_ip = validate_ipv4(broadcast_ip, "Broadcast IP")
    address = str(entry.get("address", "")).strip()
    password_salt = str(entry.get("password_salt", "")).strip()
    password_hash = str(entry.get("password_hash", "")).strip()
    try:
      password_iterations = int(entry.get("password_iterations", 0) or 0)
    except (TypeError, ValueError):
      password_iterations = 0

    has_password = bool(password_salt and password_hash and password_iterations > 0)
    legacy_combined_lock = parse_bool(entry.get("lock_wake_ping_with_password", False), default=False)
    lock_wake_with_password = parse_bool(
      entry.get("lock_wake_with_password", legacy_combined_lock),
      default=legacy_combined_lock,
    )
    lock_ping_with_password = parse_bool(
      entry.get("lock_ping_with_password", legacy_combined_lock),
      default=legacy_combined_lock,
    )

    if not has_password:
      password_salt = ""
      password_hash = ""
      password_iterations = 0
      lock_wake_with_password = False
      lock_ping_with_password = False

    return {
        "id": device_id,
        "name": name,
        "mac_address": mac_address,
        "broadcast_ip": broadcast_ip,
        "address": address,
      "password_salt": password_salt,
      "password_hash": password_hash,
      "password_iterations": password_iterations,
      "lock_wake_with_password": lock_wake_with_password,
      "lock_ping_with_password": lock_ping_with_password,
    }


def read_devices(path: Path) -> list[dict]:
    ensure_device_file(path)
    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        return []

    parsed = json.loads(raw_text)
    if not isinstance(parsed, list):
        raise ValueError("Device file must contain a JSON array.")

    devices = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            devices.append(sanitize_loaded_device(item))
        except ValueError:
            continue

    return devices


def write_devices(path: Path, devices: list[dict]) -> None:
    ensure_device_file(path)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(devices, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def build_magic_packet(mac_address: str) -> bytes:
    mac_clean = normalize_mac_address(mac_address).replace(":", "")
    mac_bytes = bytes.fromhex(mac_clean)
    return b"\xff" * 6 + mac_bytes * 16


def send_wol_packet(mac_address: str, broadcast_ip: str, port: int) -> None:
    packet = build_magic_packet(mac_address)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast_ip, port))


def ping_target(target: str, timeout_ms: int) -> tuple[bool, str]:
    ping_bin = shutil.which("ping")
    if not ping_bin:
        raise RuntimeError("ping command is not available on this host.")

    if os.name == "nt":
        command = [ping_bin, "-n", "1", "-w", str(max(timeout_ms, 100)), target]
    else:
        timeout_seconds = max(1, (max(timeout_ms, 100) + 999) // 1000)
        command = [ping_bin, "-c", "1", "-W", str(timeout_seconds), target]

    completed = subprocess.run(command, capture_output=True, text=True)

    if completed.returncode == 0:
        return True, f"{target} is online."

    detail = (completed.stderr or completed.stdout or "No response").strip()
    if len(detail) > 180:
        detail = detail[:180].rstrip() + "..."
    return False, f"{target} is offline ({detail})."


def find_device(devices: list[dict], device_id: str) -> tuple[int, dict | None]:
    for index, device in enumerate(devices):
        if device.get("id") == device_id:
            return index, device
    return -1, None


@app.get("/")
def index() -> str:
    return render_template("index.html", default_broadcast_ip=DEFAULT_BROADCAST_IP)


@app.after_request
def add_cors_headers(response):
  allow_origin = get_env_config()["cors_allow_origin"]
  if allow_origin:
    response.headers["Access-Control-Allow-Origin"] = allow_origin
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
  return response


@app.get("/api/devices")
def get_devices():
    config = get_env_config()
    devices_path = get_devices_file_path(config)
    try:
        with DEVICE_FILE_LOCK:
            devices = read_devices(devices_path)
    except (OSError, json.JSONDecodeError, ValueError) as err:
        return jsonify({"error": f"Failed to read devices: {err}"}), 500

    return jsonify({"devices": [build_public_device(device) for device in devices]})


@app.post("/api/devices")
def create_device():
    payload = request.get_json(silent=True) or {}
    mac_raw = str(payload.get("mac_address", "")).strip()
    if not mac_raw:
        return jsonify({"error": "MAC address is required."}), 400

    try:
        mac_address = normalize_mac_address(mac_raw)
        name = str(payload.get("name", "")).strip()
        address = str(payload.get("address", "")).strip()

        broadcast_ip = str(payload.get("broadcast_ip", "")).strip() or DEFAULT_BROADCAST_IP
        broadcast_ip = validate_ipv4(broadcast_ip, "Broadcast IP")

        password_raw = str(payload.get("password", ""))
        legacy_combined_lock = parse_bool(payload.get("lock_wake_ping_with_password", False), default=False)
        lock_wake_with_password = parse_bool(
          payload.get("lock_wake_with_password", legacy_combined_lock),
          default=legacy_combined_lock,
        )
        lock_ping_with_password = parse_bool(
          payload.get("lock_ping_with_password", legacy_combined_lock),
          default=legacy_combined_lock,
        )
        lock_fields_supplied = any(
          key in payload
          for key in ("lock_wake_with_password", "lock_ping_with_password", "lock_wake_ping_with_password")
        )

        password_salt = ""
        password_hash = ""
        password_iterations = 0
        if password_raw.strip():
            password = sanitize_new_password(password_raw)
            password_salt, password_hash, password_iterations = hash_password(password)
            if not lock_fields_supplied:
                lock_wake_with_password = True
                lock_ping_with_password = True
        elif lock_wake_with_password or lock_ping_with_password:
            return jsonify({"error": "Set a password before enabling wake/ping password locks."}), 400
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    new_device = {
        "id": uuid.uuid4().hex,
        "name": name,
        "mac_address": mac_address,
        "broadcast_ip": broadcast_ip,
        "address": address,
        "password_salt": password_salt,
        "password_hash": password_hash,
        "password_iterations": password_iterations,
        "lock_wake_with_password": lock_wake_with_password and bool(password_hash),
        "lock_ping_with_password": lock_ping_with_password and bool(password_hash),
    }

    config = get_env_config()
    devices_path = get_devices_file_path(config)
    try:
        with DEVICE_FILE_LOCK:
            devices = read_devices(devices_path)
            devices.append(new_device)
            write_devices(devices_path, devices)
    except (OSError, json.JSONDecodeError, ValueError) as err:
        return jsonify({"error": f"Failed to save device: {err}"}), 500

    return jsonify({"device": build_public_device(new_device)}), 201


@app.post("/api/devices/<device_id>/details")
def get_device_details(device_id: str):
  payload = request.get_json(silent=True) or {}

  config = get_env_config()
  devices_path = get_devices_file_path(config)
  try:
    with DEVICE_FILE_LOCK:
      devices = read_devices(devices_path)
      _index, device = find_device(devices, device_id)
  except (OSError, json.JSONDecodeError, ValueError) as err:
    return jsonify({"error": f"Failed to load device: {err}"}), 500

  if device is None:
    return jsonify({"error": "Device not found."}), 404

  password_error, authenticated_with_password = require_device_password(device, payload, config)
  if password_error:
    return jsonify({"error": password_error}), password_error_status(password_error)

  response = jsonify({"device": build_edit_device(device)})
  remember_requested = parse_bool(payload.get("remember_password", False), default=False)
  if authenticated_with_password and remember_requested:
    set_remember_cookie(response, device, config)
  return response


@app.put("/api/devices/<device_id>")
def update_device(device_id: str):
  payload = request.get_json(silent=True) or {}
  authenticated_with_password = False
  remember_requested = parse_bool(payload.get("remember_password", False), default=False)
  should_clear_remember_cookie = False
  updated_device = None

  config = get_env_config()
  devices_path = get_devices_file_path(config)
  try:
    with DEVICE_FILE_LOCK:
      devices = read_devices(devices_path)
      index, device = find_device(devices, device_id)
      if index < 0 or device is None:
        return jsonify({"error": "Device not found."}), 404

      password_error, authenticated_with_password = require_device_password(device, payload, config)
      if password_error:
        return jsonify({"error": password_error}), password_error_status(password_error)

      try:
        name = str(payload.get("name", device.get("name", ""))).strip()
        mac_raw = str(payload.get("mac_address", device.get("mac_address", ""))).strip()
        address = str(payload.get("address", device.get("address", ""))).strip()
        broadcast_raw = str(payload.get("broadcast_ip", device.get("broadcast_ip", ""))).strip()
        new_password_raw = str(payload.get("new_password", ""))
        remove_password = parse_bool(payload.get("remove_password", False), default=False)
        had_password_before = device_has_password(device)
        lock_fields_supplied = any(
          key in payload
          for key in ("lock_wake_with_password", "lock_ping_with_password", "lock_wake_ping_with_password")
        )
        legacy_combined_lock = parse_bool(payload.get("lock_wake_ping_with_password", False), default=False)
        lock_wake_with_password = parse_bool(
          payload.get(
            "lock_wake_with_password",
            legacy_combined_lock
            if "lock_wake_with_password" in payload or "lock_wake_ping_with_password" in payload
            else device.get("lock_wake_with_password", False),
          ),
          default=bool(device.get("lock_wake_with_password", False)),
        )
        lock_ping_with_password = parse_bool(
          payload.get(
            "lock_ping_with_password",
            legacy_combined_lock
            if "lock_ping_with_password" in payload or "lock_wake_ping_with_password" in payload
            else device.get("lock_ping_with_password", False),
          ),
          default=bool(device.get("lock_ping_with_password", False)),
        )

        if not mac_raw:
          return jsonify({"error": "MAC address is required."}), 400

        mac_address = normalize_mac_address(mac_raw)
        broadcast_ip = validate_ipv4(broadcast_raw or DEFAULT_BROADCAST_IP, "Broadcast IP")

        if remove_password and new_password_raw.strip():
          return jsonify({"error": "Cannot set and remove password in the same update."}), 400

        if had_password_before and (remove_password or new_password_raw.strip()):
          current_password_error = require_explicit_current_password(device, payload)
          if current_password_error:
            return jsonify({"error": current_password_error}), password_error_status(current_password_error)

        password_salt = str(device.get("password_salt", "")).strip()
        password_hash = str(device.get("password_hash", "")).strip()
        try:
          password_iterations = int(device.get("password_iterations", 0) or 0)
        except (TypeError, ValueError):
          password_iterations = 0

        if remove_password:
          password_salt = ""
          password_hash = ""
          password_iterations = 0
          lock_wake_with_password = False
          lock_ping_with_password = False
          should_clear_remember_cookie = True
        elif new_password_raw.strip():
          next_password = sanitize_new_password(new_password_raw)
          password_salt, password_hash, password_iterations = hash_password(next_password)
          if not had_password_before and not lock_fields_supplied:
            lock_wake_with_password = True
            lock_ping_with_password = True

        if password_hash:
          lock_wake_with_password = bool(lock_wake_with_password)
          lock_ping_with_password = bool(lock_ping_with_password)
        else:
          if lock_wake_with_password or lock_ping_with_password:
            return jsonify({"error": "Set a password before enabling wake/ping password locks."}), 400
          lock_wake_with_password = False
          lock_ping_with_password = False
      except ValueError as err:
        return jsonify({"error": str(err)}), 400

      updated_device = {
        "id": device_id,
        "name": name,
        "mac_address": mac_address,
        "broadcast_ip": broadcast_ip,
        "address": address,
        "password_salt": password_salt,
        "password_hash": password_hash,
        "password_iterations": password_iterations,
        "lock_wake_with_password": lock_wake_with_password and bool(password_hash),
        "lock_ping_with_password": lock_ping_with_password and bool(password_hash),
      }

      devices[index] = updated_device
      write_devices(devices_path, devices)
  except (OSError, json.JSONDecodeError, ValueError) as err:
    return jsonify({"error": f"Failed to update device: {err}"}), 500

  response = jsonify({"device": build_public_device(updated_device), "message": "Device updated."})
  if should_clear_remember_cookie or not device_has_password(updated_device):
    clear_remember_cookie(response, device_id, config)
  elif authenticated_with_password and remember_requested:
    set_remember_cookie(response, updated_device, config)
  return response


@app.delete("/api/devices/<device_id>")
def delete_device(device_id: str):
  payload = request.get_json(silent=True) or {}

  config = get_env_config()
  devices_path = get_devices_file_path(config)
  try:
    with DEVICE_FILE_LOCK:
      devices = read_devices(devices_path)
      index, device = find_device(devices, device_id)
      if index < 0 or device is None:
        return jsonify({"error": "Device not found."}), 404

      password_error, _authenticated_with_password = require_device_password(device, payload, config)
      if password_error:
        return jsonify({"error": password_error}), password_error_status(password_error)

      devices.pop(index)
      write_devices(devices_path, devices)
  except (OSError, json.JSONDecodeError, ValueError) as err:
    return jsonify({"error": f"Failed to delete device: {err}"}), 500

  response = jsonify({"message": "Device deleted."})
  clear_remember_cookie(response, device_id, config)
  return response


@app.delete("/api/devices/<device_id>/password")
def remove_device_password(device_id: str):
    payload = request.get_json(silent=True) or {}

    config = get_env_config()
    devices_path = get_devices_file_path(config)
    try:
        with DEVICE_FILE_LOCK:
            devices = read_devices(devices_path)
            index, device = find_device(devices, device_id)
            if index < 0 or device is None:
                return jsonify({"error": "Device not found."}), 404

            if not device_has_password(device):
                return jsonify({"error": "This device has no password set."}), 400

            current_password_error = require_explicit_current_password(device, payload)
            if current_password_error:
              return jsonify({"error": current_password_error}), password_error_status(current_password_error)

            device["password_salt"] = ""
            device["password_hash"] = ""
            device["password_iterations"] = 0
            device["lock_wake_with_password"] = False
            device["lock_ping_with_password"] = False

            devices[index] = device
            write_devices(devices_path, devices)
    except (OSError, json.JSONDecodeError, ValueError) as err:
        return jsonify({"error": f"Failed to update password: {err}"}), 500

    response = jsonify({"device": build_public_device(device), "message": "Password removed."})
    clear_remember_cookie(response, device_id, config)
    return response


@app.post("/api/devices/<device_id>/wake")
def wake_device(device_id: str):
  payload = request.get_json(silent=True) or {}
  authenticated_with_password = False

  config = get_env_config()
  devices_path = get_devices_file_path(config)
  try:
    with DEVICE_FILE_LOCK:
      devices = read_devices(devices_path)
      _index, device = find_device(devices, device_id)
  except (OSError, json.JSONDecodeError, ValueError) as err:
    return jsonify({"error": f"Failed to load device: {err}"}), 500

  if device is None:
    return jsonify({"error": "Device not found."}), 404

  if device_has_password(device) and bool(device.get("lock_wake_with_password", False)):
    password_error, authenticated_with_password = require_device_password(device, payload, config)
    if password_error:
      return jsonify({"error": password_error}), password_error_status(password_error)

  try:
    send_wol_packet(device["mac_address"], device["broadcast_ip"], config["wol_port"])
  except ValueError as err:
    return jsonify({"error": str(err)}), 400
  except OSError as err:
    return jsonify({"error": f"Socket error: {err}"}), 500

  label = device.get("name") or device.get("address") or device["mac_address"]
  response = jsonify({"message": f"Wake packet sent to {label}."})
  remember_requested = parse_bool(payload.get("remember_password", False), default=False)
  if authenticated_with_password and remember_requested:
    set_remember_cookie(response, device, config)
  return response


@app.post("/api/devices/<device_id>/ping")
def ping_device(device_id: str):
  payload = request.get_json(silent=True) or {}
  authenticated_with_password = False

  config = get_env_config()
  devices_path = get_devices_file_path(config)
  try:
    with DEVICE_FILE_LOCK:
      devices = read_devices(devices_path)
      _index, device = find_device(devices, device_id)
  except (OSError, json.JSONDecodeError, ValueError) as err:
    return jsonify({"error": f"Failed to load device: {err}"}), 500

  if device is None:
    return jsonify({"error": "Device not found.", "online": False}), 404

  if device_has_password(device) and bool(device.get("lock_ping_with_password", False)):
    password_error, authenticated_with_password = require_device_password(device, payload, config)
    if password_error:
      return jsonify({"error": password_error, "online": False}), password_error_status(password_error)

  target = (device.get("address") or "").strip() or (device.get("name") or "").strip()
  if not target:
    return (
      jsonify(
        {
          "error": "No ping target for this device. Set Direct Address or a resolvable Name.",
          "online": False,
        }
      ),
      400,
    )

  try:
    online, message = ping_target(target, config["ping_timeout_ms"])
  except RuntimeError as err:
    return jsonify({"error": str(err), "online": False}), 500
  except OSError as err:
    return jsonify({"error": f"Ping command failed: {err}", "online": False}), 500

  response = jsonify({"online": online, "target": target, "message": message})
  remember_requested = parse_bool(payload.get("remember_password", False), default=False)
  if authenticated_with_password and remember_requested:
    set_remember_cookie(response, device, config)
  return response


if __name__ == "__main__":
    cfg = get_env_config()
    app.run(host=cfg["host"], port=cfg["app_port"], debug=False)

