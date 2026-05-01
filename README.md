<!-- SPONSOR-START -->
---

<div align="center">

### 🌐 Need Proxies? Check out my services

<a href="https://vaultproxies.com" target="_blank" rel="noopener noreferrer">
  <img src="https://i.imgur.com/TF165pP.gif" alt="VaultProxies">
</a>
<p></p>

<table>
  <tr>
    <th>Service</th>
    <th>Pricing</th>
    <th>Features</th>
  </tr>
  <tr>
    <td><b><a href="https://vaultproxies.com" target="_blank" rel="noopener noreferrer">🔮 VaultProxies</a></b></td>
    <td><code>$1.00/GB</code> residential</td>
    <td>Residential · IPv6 · Residential Unlimited · Datacenter</td>
  </tr>
  <tr>
    <td><b><a href="https://nullproxies.com" target="_blank" rel="noopener noreferrer">🌑 NullProxies</a></b></td>
    <td><code>$0.75/GB</code> residential</td>
    <td>Residential · Residential Unlimited · DC Unlimited · Mobile Proxies</td>
  </tr>
  <tr>
    <td><b><a href="https://strikeproxy.net" target="_blank" rel="noopener noreferrer">⚡ StrikeProxy</a></b></td>
    <td><code>$0.75/GB</code> residential</td>
    <td>Residential · Residential Unlimited · DC Unlimited · Mobile Proxies</td>
  </tr>
</table>
</div>

<!-- SPONSOR-END -->

<div align="center">
  <h2 align="center">Discord Websocket Reader</h2>
  <p align="center">
    A Python tool for connecting to the Discord Gateway, decompressing and decoding ETF payloads, and logging real-time Discord events with advanced logging and debug support. Supports replaying captured WebSocket sessions from <code>.bin</code> and <code>.har</code> files. Made it in 30 minutes with AI.
    <br />
    <br />
    <a href="https://discord.cyberious.xyz">💬 Discord</a>
    ·
    <a href="#-changelog">📜 ChangeLog</a>
    ·
    <a href="https://github.com/sexfrance/Discord-Websocket-Reader/issues">⚠️ Report Bug</a>
    ·
    <a href="https://github.com/sexfrance/Discord-Websocket-Reader/issues">💡 Request Feature</a>
  </p>
</div>

---

### ⚙️ Installation

- Requires: `Python 3.8+`
- Create a virtual environment: `python -m venv venv`
- Activate the environment: `venv\Scripts\activate` (Windows) / `source venv/bin/activate` (macOS, Linux)
- Install dependencies: `pip install -r requirements.txt`

---

### 🔥 Features

- Connects to the Discord Gateway using ETF encoding and zstd-stream compression
- Handles decompression and decoding of Discord payloads
- Advanced logging system with color and debug support
- Saves large event payloads to disk for analysis
- Handles heartbeats, READY, MESSAGE_CREATE, and other Discord events
- Configurable via `input/config.toml` (token, debug mode, etc.)
- Clean JSON output for all Discord events
- Automatic log file management
- Used to fetch **discord session id** and **discord session heartbeat** in discord x-super-properties headers
- Decode captured WebSocket sessions from `.bin` and `.har` files offline

---

### 📝 Usage

1. **Configuration**:

   - Edit `input/config.toml` and set your Discord user token under `[data]`:

   ```toml
   [dev]
   Debug = false

   [data]
   token = "YOUR_DISCORD_TOKEN"
   ```

2. **Run the script**:

   ```bash
   python main.py
   ```

3. **Output**:
   - All received Discord events are logged to the console
   - Large event payloads are saved to the `logs/` directory as JSON files

#### Decode a captured `.bin` or `.har` file

```bash
python main.py --decode-bin capture.bin
python main.py --decode-bin capture.har
```

Replays a captured WebSocket session offline without reconnecting. `.bin` files use the `\n\n---\n\n` separator format; `.har` files are exported from browser DevTools (Chrome / Firefox) with base64-encoded binary frames. Format is auto-detected from the extension. All decoded events are saved to `logs/`.

---

### 📹 Preview

![Preview](https://i.imgur.com/SYWqf6T.gif)

---

### ❗ Disclaimers

- This project is for educational and research purposes only
- The author is not responsible for any misuse of this tool
- Use responsibly and in accordance with Discord's Terms of Service

---

### 📜 ChangeLog

```diff
v0.0.2 ⋮ 05/01/2026
+ Added --decode-bin flag to replay captured .bin and .har files offline
+ HAR support: base64 binary frames decoded via streaming zlib context
+ .bin support: separator-based format with graceful handling of corrupted binary frames
+ Auto-detects file format from extension

v0.0.1 ⋮ 07/17/2025
! Initial release: Discord Gateway connection, ETF/zstd support, event logging, and debug features
```

<p align="center">
  <img src="https://img.shields.io/github/license/sexfrance/Discord-Websocket-Reader.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=IOTA"/>
  <img src="https://img.shields.io/github/stars/sexfrance/Discord-Websocket-Reader.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=IOTA"/>
  <img src="https://img.shields.io/github/languages/top/sexfrance/Discord-Websocket-Reader.svg?style=for-the-badge&labelColor=black&color=f429ff&logo=python"/>
</p>
