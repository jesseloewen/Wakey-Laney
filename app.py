import json
import os
import shutil
import socket
import subprocess
import threading
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request


load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"), override=False)

app = Flask(__name__)

DEFAULT_BROADCAST_IP = "192.168.0.255"
DEFAULT_WOL_PORT = 9
DEFAULT_PING_TIMEOUT_MS = 1200
DEVICE_FILE_LOCK = threading.Lock()


HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wake Device Manager</title>
  <style>
    @import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap");

    :root {
      --bg-1: #050711;
      --bg-2: #10192d;
      --panel: rgba(10, 16, 30, 0.8);
      --panel-2: rgba(16, 24, 42, 0.88);
      --line: rgba(163, 181, 215, 0.24);
      --text: #ecf3ff;
      --muted: #9fb0cf;
      --accent: #2ad4a6;
      --accent-2: #2aa7d4;
      --danger: #ff7b8b;
      --success: #79f4c1;
      --warning: #ffda83;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      font-family: "Space Grotesk", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 10% 10%, rgba(42, 167, 212, 0.22), transparent 32%),
        radial-gradient(circle at 90% 90%, rgba(42, 212, 166, 0.2), transparent 34%),
        linear-gradient(140deg, var(--bg-1), var(--bg-2));
      padding: 20px;
    }

    .layout {
      max-width: 980px;
      margin: 0 auto;
      display: grid;
      gap: 18px;
      grid-template-columns: 1fr;
      align-items: start;
    }

    .panel {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: var(--panel);
      backdrop-filter: blur(10px);
      box-shadow: 0 18px 48px rgba(0, 0, 0, 0.45);
      overflow: hidden;
    }

    .panel h1,
    .panel h2 {
      margin: 0;
      letter-spacing: 0.02em;
    }

    .panel-head {
      padding: 18px 18px 12px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(120deg, rgba(42, 167, 212, 0.16), rgba(42, 212, 166, 0.1));
    }

    .panel-head p {
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.45;
      font-size: 0.94rem;
    }

    .panel-body {
      padding: 16px 18px 18px;
    }

    .field {
      margin-bottom: 12px;
    }

    label {
      display: block;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 0.84rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.03);
      color: var(--text);
      padding: 11px 12px;
      font: inherit;
      outline: none;
      transition: border-color 140ms ease, box-shadow 140ms ease;
    }

    input:focus {
      border-color: rgba(42, 212, 166, 0.78);
      box-shadow: 0 0 0 3px rgba(42, 212, 166, 0.16);
    }

    .hint {
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.85rem;
      line-height: 1.35;
    }

    button {
      border: 1px solid transparent;
      border-radius: 10px;
      padding: 10px 12px;
      background: var(--accent);
      color: #042017;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      transition: transform 120ms ease, opacity 120ms ease, background 120ms ease;
    }

    button:hover {
      transform: translateY(-1px);
    }

    button:disabled {
      opacity: 0.66;
      cursor: not-allowed;
      transform: none;
    }

    .ghost-btn {
      background: transparent;
      color: var(--text);
      border-color: rgba(42, 212, 166, 0.56);
    }

    .ghost-btn:hover {
      background: rgba(42, 212, 166, 0.16);
    }

    .list-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
    }

    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 10px;
      color: var(--muted);
      font-size: 0.82rem;
      background: rgba(255, 255, 255, 0.03);
    }

    #devices {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    }

    .empty {
      border: 1px dashed var(--line);
      border-radius: 12px;
      padding: 18px;
      text-align: center;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.02);
      grid-column: 1 / -1;
    }

    .device {
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--panel-2);
      padding: 13px;
      display: grid;
      gap: 10px;
      animation: rise 300ms ease both;
    }

    .device-top {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      flex-wrap: wrap;
    }

    .device h3 {
      margin: 0;
      font-size: 1.03rem;
    }

    .device small {
      color: var(--muted);
      display: block;
      margin-top: 4px;
      font-size: 0.82rem;
      word-break: break-word;
    }

    .device-meta {
      display: grid;
      gap: 8px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      font-size: 0.88rem;
      color: var(--muted);
    }

    .device-meta strong {
      color: var(--text);
      margin-left: 5px;
      font-weight: 500;
      word-break: break-word;
    }

    .device-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .device-actions-main {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      align-items: stretch;
    }

    .device-actions-main button {
      width: 100%;
      min-width: 0;
      text-align: center;
      padding: 8px 6px;
      font-size: 0.83rem;
      line-height: 1.1;
    }

    .device-actions button[data-action="wake"] {
      background: var(--accent);
    }

    .device-actions button[data-action="ping"] {
      background: transparent;
      color: var(--text);
      border-color: rgba(42, 212, 166, 0.56);
    }

    .device-actions button[data-action="delete"] {
      background: transparent;
      color: var(--danger);
      border-color: rgba(255, 123, 139, 0.5);
    }

    .device-actions button[data-action="edit"] {
      background: transparent;
      color: var(--text);
      border-color: rgba(42, 167, 212, 0.52);
    }

    .device-edit {
      display: none;
      gap: 10px;
    }

    .device[data-editing="true"] .device-view,
    .device[data-editing="true"] .device-actions-main {
      display: none;
    }

    .device[data-editing="true"] .device-edit {
      display: grid;
    }

    .edit-grid {
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }

    .edit-grid .field {
      margin: 0;
    }

    .row-status {
      min-height: 20px;
      color: var(--muted);
      font-size: 0.88rem;
      font-weight: 600;
    }

    .status-success { color: var(--success); }
    .status-error { color: var(--danger); }
    .status-warning { color: var(--warning); }

    #globalStatus {
      min-height: 20px;
      margin-top: 10px;
      font-size: 0.9rem;
      font-weight: 600;
      color: var(--muted);
    }

    @keyframes rise {
      from { opacity: 0; transform: translateY(7px); }
      to { opacity: 1; transform: translateY(0); }
    }

    #setupPanel[hidden] {
      display: none;
    }
  </style>
</head>
<body>
  <main class="layout">
    <section class="panel">
      <div class="panel-head">
        <div class="list-head">
          <h1>Devices</h1>
          <span id="deviceCount" class="pill">0 devices</span>
        </div>
        <p>Each row supports wake, ping, edit, and delete actions.</p>
      </div>
      <div class="panel-body">
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;">
          <button id="toggleSetupBtn" type="button" class="ghost-btn">Add Device</button>
        </div>
        <div id="devices"></div>
        <div id="globalStatus" aria-live="polite"></div>
      </div>
    </section>

    <section id="setupPanel" class="panel" hidden>
      <div class="panel-head">
        <h2>Device Setup</h2>
        <p>Add devices to your wake and ping list. Only MAC address is required.</p>
      </div>
      <div class="panel-body">
        <form id="addDeviceForm">
          <div class="field">
            <label for="name">Name (optional)</label>
            <input id="name" name="name" type="text" placeholder="Office PC">
          </div>

          <div class="field">
            <label for="mac">MAC Address (required)</label>
            <input id="mac" name="mac_address" type="text" required placeholder="AA:BB:CC:DD:EE:FF">
          </div>

          <div class="field">
            <label for="address">Direct Address (optional)</label>
            <input id="address" name="address" type="text" placeholder="Hostname or IP address">
          </div>

          <div class="field">
            <label for="broadcast">Broadcast IP (optional)</label>
            <input id="broadcast" name="broadcast_ip" type="text" placeholder="{{ default_broadcast_ip }}">
          </div>

          <button id="addBtn" type="submit">Add Device</button>
        </form>
        <div class="hint">Default broadcast is {{ default_broadcast_ip }} when left empty.</div>
      </div>
    </section>
  </main>

  <script>
    const defaultBroadcast = {{ default_broadcast_ip|tojson }};
    const setupPanel = document.getElementById("setupPanel");
    const toggleSetupBtn = document.getElementById("toggleSetupBtn");
    const addForm = document.getElementById("addDeviceForm");
    const addBtn = document.getElementById("addBtn");
    const globalStatus = document.getElementById("globalStatus");
    const devicesRoot = document.getElementById("devices");
    const deviceCount = document.getElementById("deviceCount");
    const state = { devices: [] };

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function setGlobalStatus(type, message) {
      globalStatus.className = "";
      if (type) {
        globalStatus.classList.add("status-" + type);
      }
      globalStatus.textContent = message || "";
    }

    function setRowStatus(row, type, message) {
      const status = row.querySelector(".row-status");
      if (!status) {
        return;
      }

      status.className = "row-status";
      if (type) {
        status.classList.add("status-" + type);
      }
      status.textContent = message || "";
    }

    function setSetupOpen(isOpen) {
      setupPanel.hidden = !isOpen;
      toggleSetupBtn.textContent = isOpen ? "Close Setup" : "Add Device";
    }

    function displayName(device) {
      return device.name || device.address || device.mac_address;
    }

    function renderDevices() {
      const total = state.devices.length;
      deviceCount.textContent = total + (total === 1 ? " device" : " devices");
      devicesRoot.innerHTML = "";

      if (total === 0) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "No devices yet. Add your first device on the left.";
        devicesRoot.appendChild(empty);
        return;
      }

      for (const device of state.devices) {
        const card = document.createElement("article");
        card.className = "device";
        card.dataset.deviceId = device.id;

        const label = escapeHtml(displayName(device));
        const name = escapeHtml(device.name || "");
        const address = escapeHtml(device.address || "Not set");
        const addressInput = escapeHtml(device.address || "");
        const mac = escapeHtml(device.mac_address);
        const broadcast = escapeHtml(device.broadcast_ip || defaultBroadcast);

        card.innerHTML = `
          <div class="device-view">
            <div class="device-top">
              <div>
                <h3>${label}</h3>
                <small>Address: ${address}</small>
              </div>
            </div>
            <div class="device-meta">
              <div>MAC:<strong>${mac}</strong></div>
              <div>Broadcast:<strong>${broadcast}</strong></div>
            </div>
          </div>
          <div class="device-edit">
            <div class="edit-grid">
              <div class="field">
                <label>Name</label>
                <input type="text" data-field="name" value="${name}" placeholder="Office PC">
              </div>
              <div class="field">
                <label>MAC Address</label>
                <input type="text" data-field="mac_address" value="${mac}" placeholder="AA:BB:CC:DD:EE:FF">
              </div>
              <div class="field">
                <label>Direct Address</label>
                <input type="text" data-field="address" value="${addressInput}" placeholder="Hostname or IP address">
              </div>
              <div class="field">
                <label>Broadcast IP</label>
                <input type="text" data-field="broadcast_ip" value="${broadcast}" placeholder="${defaultBroadcast}">
              </div>
            </div>
            <div class="device-actions">
              <button type="button" data-action="save">Save</button>
              <button type="button" data-action="cancel-edit" class="ghost-btn">Cancel</button>
            </div>
          </div>
          <div class="device-actions device-actions-main">
            <button type="button" data-action="wake">Wake</button>
            <button type="button" data-action="ping">Ping</button>
            <button type="button" data-action="edit">Edit</button>
            <button type="button" data-action="delete">Delete</button>
          </div>
          <div class="row-status"></div>
        `;

        devicesRoot.appendChild(card);
      }
    }

    function collectRowPayload(row) {
      const payload = {};
      const fields = row.querySelectorAll("[data-field]");
      fields.forEach((input) => {
        payload[input.dataset.field] = input.value.trim();
      });
      return payload;
    }

    function setRowEditing(row, editing) {
      row.dataset.editing = editing ? "true" : "false";
      if (!editing) {
        setRowStatus(row, "", "");
      }
    }

    async function api(path, options) {
      const response = await fetch(path, options || {});
      let payload = {};

      try {
        payload = await response.json();
      } catch (_) {
        payload = {};
      }

      if (!response.ok) {
        throw new Error(payload.error || "Request failed");
      }

      return payload;
    }

    async function loadDevices() {
      const payload = await api("/api/devices");
      state.devices = payload.devices || [];
      renderDevices();
    }

    addForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      addBtn.disabled = true;
      setGlobalStatus("", "Adding device...");

      const formData = new FormData(addForm);
      const body = {
        name: (formData.get("name") || "").toString().trim(),
        mac_address: (formData.get("mac_address") || "").toString().trim(),
        address: (formData.get("address") || "").toString().trim(),
        broadcast_ip: (formData.get("broadcast_ip") || "").toString().trim()
      };

      try {
        await api("/api/devices", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        });

        addForm.reset();
        await loadDevices();
        setSetupOpen(false);
        setGlobalStatus("success", "Device added.");
      } catch (error) {
        setGlobalStatus("error", error.message || "Failed to add device.");
      } finally {
        addBtn.disabled = false;
      }
    });

    toggleSetupBtn.addEventListener("click", () => {
      setSetupOpen(setupPanel.hidden);
    });

    devicesRoot.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) {
        return;
      }

      const row = event.target.closest(".device");
      if (!row) {
        return;
      }

      const deviceId = row.dataset.deviceId;
      const action = button.dataset.action;
      if (!deviceId || !action) {
        return;
      }

      if (action === "edit") {
        setRowEditing(row, true);
        return;
      }

      if (action === "cancel-edit") {
        renderDevices();
        return;
      }

      if (action === "delete") {
        const confirmed = window.confirm("Delete this device?");
        if (!confirmed) {
          return;
        }
      }

      const buttons = row.querySelectorAll("button");
      buttons.forEach((item) => {
        item.disabled = true;
      });
      setRowStatus(row, "", "Working...");

      try {
        if (action === "wake") {
          const payload = await api("/api/devices/" + deviceId + "/wake", { method: "POST" });
          setRowStatus(row, "success", payload.message || "Wake packet sent.");
        } else if (action === "ping") {
          const payload = await api("/api/devices/" + deviceId + "/ping", { method: "GET", cache: "no-store" });
          if (payload.online) {
            setRowStatus(row, "success", payload.message || "Device is online.");
          } else {
            setRowStatus(row, "warning", payload.message || "Device is offline.");
          }
        } else if (action === "save") {
          const body = collectRowPayload(row);
          if (!body.mac_address) {
            throw new Error("MAC address is required.");
          }

          await api("/api/devices/" + deviceId, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
          });
          await loadDevices();
          setGlobalStatus("success", "Device updated.");
        } else if (action === "delete") {
          await api("/api/devices/" + deviceId, { method: "DELETE" });
          await loadDevices();
          setGlobalStatus("success", "Device deleted.");
        }
      } catch (error) {
        setRowStatus(row, "error", error.message || "Action failed.");
      } finally {
        buttons.forEach((item) => {
          item.disabled = false;
        });
      }
    });

    loadDevices().catch((error) => {
      setGlobalStatus("error", error.message || "Failed to load devices.");
    });

    setSetupOpen(false);
  </script>
</body>
</html>
"""


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


def sanitize_loaded_device(entry: dict) -> dict:
    device_id = str(entry.get("id", "")).strip() or uuid.uuid4().hex
    name = str(entry.get("name", "")).strip()
    mac_address = normalize_mac_address(str(entry.get("mac_address", "")).strip())
    broadcast_ip = str(entry.get("broadcast_ip", "")).strip() or DEFAULT_BROADCAST_IP
    broadcast_ip = validate_ipv4(broadcast_ip, "Broadcast IP")
    address = str(entry.get("address", "")).strip()

    return {
        "id": device_id,
        "name": name,
        "mac_address": mac_address,
        "broadcast_ip": broadcast_ip,
        "address": address,
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
    return render_template_string(HTML_PAGE, default_broadcast_ip=DEFAULT_BROADCAST_IP)


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

    return jsonify({"devices": devices})


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
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    new_device = {
        "id": uuid.uuid4().hex,
        "name": name,
        "mac_address": mac_address,
        "broadcast_ip": broadcast_ip,
        "address": address,
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

    return jsonify({"device": new_device}), 201


@app.put("/api/devices/<device_id>")
def update_device(device_id: str):
    payload = request.get_json(silent=True) or {}

    config = get_env_config()
    devices_path = get_devices_file_path(config)
    try:
        with DEVICE_FILE_LOCK:
            devices = read_devices(devices_path)
            index, device = find_device(devices, device_id)
            if index < 0 or device is None:
                return jsonify({"error": "Device not found."}), 404

            try:
                name = str(payload.get("name", device.get("name", ""))).strip()
                mac_raw = str(payload.get("mac_address", device.get("mac_address", ""))).strip()
                address = str(payload.get("address", device.get("address", ""))).strip()
                broadcast_raw = str(payload.get("broadcast_ip", device.get("broadcast_ip", ""))).strip()

                if not mac_raw:
                    return jsonify({"error": "MAC address is required."}), 400

                mac_address = normalize_mac_address(mac_raw)
                broadcast_ip = validate_ipv4(broadcast_raw or DEFAULT_BROADCAST_IP, "Broadcast IP")
            except ValueError as err:
                return jsonify({"error": str(err)}), 400

            updated_device = {
                "id": device_id,
                "name": name,
                "mac_address": mac_address,
                "broadcast_ip": broadcast_ip,
                "address": address,
            }

            devices[index] = updated_device
            write_devices(devices_path, devices)
    except (OSError, json.JSONDecodeError, ValueError) as err:
        return jsonify({"error": f"Failed to update device: {err}"}), 500

    return jsonify({"device": updated_device, "message": "Device updated."})


@app.delete("/api/devices/<device_id>")
def delete_device(device_id: str):
    config = get_env_config()
    devices_path = get_devices_file_path(config)
    try:
        with DEVICE_FILE_LOCK:
            devices = read_devices(devices_path)
            index, _device = find_device(devices, device_id)
            if index < 0:
                return jsonify({"error": "Device not found."}), 404

            devices.pop(index)
            write_devices(devices_path, devices)
    except (OSError, json.JSONDecodeError, ValueError) as err:
        return jsonify({"error": f"Failed to delete device: {err}"}), 500

    return jsonify({"message": "Device deleted."})


@app.post("/api/devices/<device_id>/wake")
def wake_device(device_id: str):
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

    try:
        send_wol_packet(device["mac_address"], device["broadcast_ip"], config["wol_port"])
    except ValueError as err:
        return jsonify({"error": str(err)}), 400
    except OSError as err:
        return jsonify({"error": f"Socket error: {err}"}), 500

    label = device.get("name") or device.get("address") or device["mac_address"]
    return jsonify({"message": f"Wake packet sent to {label}."})


@app.get("/api/devices/<device_id>/ping")
def ping_device(device_id: str):
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

    return jsonify({"online": online, "target": target, "message": message})


if __name__ == "__main__":
    cfg = get_env_config()
    app.run(host=cfg["host"], port=cfg["app_port"], debug=False)
