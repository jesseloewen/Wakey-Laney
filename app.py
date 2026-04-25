import os
import socket
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)


HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wake Device</title>
  <style>
    :root {
      --bg: #f3f5f7;
      --card: #ffffff;
      --text: #1e2530;
      --muted: #5f6b7a;
      --accent: #0b7a75;
      --accent-hover: #0a6965;
      --error: #b42318;
      --success: #027a48;
      --border: #d8dde5;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 15% 15%, #d9eff0 0%, transparent 35%),
        radial-gradient(circle at 85% 85%, #dce8f8 0%, transparent 40%),
        var(--bg);
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 16px;
    }

    .card {
      width: 100%;
      max-width: 520px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 24px;
      box-shadow: 0 14px 28px rgba(16, 24, 40, 0.08);
    }

    h1 {
      margin: 0 0 12px;
      font-size: 1.45rem;
    }

    p {
      margin: 0 0 10px;
      color: var(--muted);
      line-height: 1.4;
    }

    .meta {
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
      margin: 16px 0 18px;
      font-size: 0.95rem;
    }

    .meta strong {
      color: var(--text);
    }

    button {
      appearance: none;
      border: 0;
      border-radius: 10px;
      padding: 12px 16px;
      width: 100%;
      background: var(--accent);
      color: #fff;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 120ms ease;
    }

    button:hover {
      background: var(--accent-hover);
    }

    #result {
      margin-top: 12px;
      min-height: 20px;
      font-size: 0.95rem;
      font-weight: 600;
    }

    #result.error { color: var(--error); }
    #result.success { color: var(--success); }
  </style>
</head>
<body>
  <main class="card">
    <h1>Wake-on-LAN</h1>
    <p>Send a WoL packet to your single configured device.</p>

    <div class="meta">
      <div><strong>Device:</strong> {{ device_name }}</div>
      <div><strong>MAC:</strong> {{ mac_address }}</div>
      <div><strong>Broadcast:</strong> {{ broadcast_ip }}:{{ wol_port }}</div>
    </div>

    <button id="wakeBtn" type="button">Wake Device</button>
    <div id="result" aria-live="polite"></div>
  </main>

  <script>
    const wakeBtn = document.getElementById("wakeBtn");
    const result = document.getElementById("result");

    wakeBtn.addEventListener("click", async () => {
      wakeBtn.disabled = true;
      result.className = "";
      result.textContent = "Sending WoL packet...";

      try {
        const response = await fetch("/wake", { method: "POST" });
        const payload = await response.json();

        if (!response.ok) {
          result.className = "error";
          result.textContent = payload.error || "Failed to send packet.";
        } else {
          result.className = "success";
          result.textContent = payload.message || "WoL packet sent.";
        }
      } catch (err) {
        result.className = "error";
        result.textContent = "Network error while sending WoL packet.";
      } finally {
        wakeBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


def get_env_config() -> dict:
    return {
        "device_name": os.getenv("WOL_DEVICE_NAME", "Configured Device"),
        "mac_address": os.getenv("WOL_MAC_ADDRESS", ""),
        "broadcast_ip": os.getenv("WOL_BROADCAST_IP", "255.255.255.255"),
        "wol_port": int(os.getenv("WOL_PORT", "9")),
        "host": os.getenv("APP_HOST", "0.0.0.0"),
        "app_port": int(os.getenv("APP_PORT", "7448")),
    }


def mac_to_bytes(mac: str) -> bytes:
    normalized = mac.replace("-", "").replace(":", "").replace(".", "").strip()
    if len(normalized) != 12:
        raise ValueError("WOL_MAC_ADDRESS must contain 12 hex characters.")

    try:
        return bytes.fromhex(normalized)
    except ValueError as err:
        raise ValueError("WOL_MAC_ADDRESS contains invalid hex characters.") from err


def build_magic_packet(mac: str) -> bytes:
    mac_bytes = mac_to_bytes(mac)
    return b"\xff" * 6 + mac_bytes * 16


def send_wol_packet(mac: str, broadcast_ip: str, port: int) -> None:
    packet = build_magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast_ip, port))


@app.get("/")
def index():
    config = get_env_config()
    return render_template_string(
        HTML_PAGE,
        device_name=config["device_name"],
        mac_address=config["mac_address"] or "(not set)",
        broadcast_ip=config["broadcast_ip"],
        wol_port=config["wol_port"],
    )


@app.post("/wake")
def wake_device():
    config = get_env_config()
    mac = config["mac_address"].strip()

    if not mac:
        return jsonify({"error": "WOL_MAC_ADDRESS is not configured."}), 500

    try:
        send_wol_packet(mac, config["broadcast_ip"], config["wol_port"])
    except ValueError as err:
        return jsonify({"error": str(err)}), 500
    except OSError as err:
        return jsonify({"error": f"Socket error: {err}"}), 500

    return jsonify({"message": f"Wake signal sent to {config['device_name']}."})


if __name__ == "__main__":
    cfg = get_env_config()
    app.run(host=cfg["host"], port=cfg["app_port"], debug=False)
