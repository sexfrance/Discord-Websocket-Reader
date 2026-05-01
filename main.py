import argparse
import asyncio
import base64
import json
import os
import sys
import zlib
import websockets
import zstandard as zstd
import erlpack
import toml

from logmagix import Logger
from functools import wraps
from typing import Dict, Any, Optional
from modules.utils import MiscUtils

config = toml.load("input/config.toml")

GATEWAY_URL: str = "wss://gateway.discord.gg/?encoding=etf&v=9&compress=zstd-stream"


TOKEN: str = config['data'].get('token', '').strip()

DEBUG = config["dev"].get("Debug", False)

log = Logger()

def debug(func_or_message, *args, **kwargs) -> callable:
    if callable(func_or_message):
        @wraps(func_or_message)
        def wrapper(*args, **kwargs):
            result = func_or_message(*args, **kwargs)
            if DEBUG:
                log.debug(f"{func_or_message.__name__} returned: {result}")
            return result
        return wrapper
    else:
        if DEBUG:
            log.debug(f"Debug: {func_or_message}")

class DiscordClient:
    def __init__(self, token: str):
        self.token: str = token
        self.ws: Optional[websockets.WebSocketServerProtocol] = None
        self.heartbeat_interval: Optional[int] = None
        self.last_heartbeat_ack: bool = True
        self.sequence: Optional[int] = None
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.message_count: int = 0
        
        self.logger = log
        self.utils = MiscUtils()
        
        os.makedirs("logs", exist_ok=True)

    async def connect(self) -> None:
        try:
            self.ws = await websockets.connect(GATEWAY_URL)
            self.logger.success("Connected to Discord Gateway")
            await self.listen()
        except Exception as e:
            self.logger.error(f"Connection error: {e}")
        finally:
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
                try:
                    await self.heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def decompress_message(self, message: bytes) -> Optional[bytes]:
        return self.utils.decompress_message(message)

    async def identify(self) -> None:
        payload: Dict[str, Any] = {
            "op": 2,
            "d": {
                "token": self.token,
                "capabilities": 8193,
                "properties": {
                    "os": "Windows",
                    "browser": "Discord Client",
                    "device": "desktop",
                },
                "presence": {
                    "status": "online",
                    "since": 0,
                    "activities": [],
                    "afk": False
                },
                "compress": True
            }
        }
        await self.send_erlpack(payload)

    async def send_heartbeat(self) -> None:
        while True:
            try:
                if self.heartbeat_interval:
                    if not self.last_heartbeat_ack:
                        self.logger.error("No ACK, disconnecting")
                        await self.ws.close()
                        return
                    heartbeat: Dict[str, Any] = {
                        "op": 1,
                        "d": self.sequence
                    }
                    await self.send_erlpack(heartbeat)
                    self.last_heartbeat_ack = False
                    self.logger.info("Heartbeat sent")
                    await asyncio.sleep(self.heartbeat_interval / 1000)
                else:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                self.logger.warning("Heartbeat task cancelled")
                break
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")
                break

    async def send_erlpack(self, data: Dict[str, Any]) -> None:
        packed = erlpack.pack(data)
        await self.ws.send(packed)

    async def handle_message(self, data: Dict[str, Any]) -> None:
        op: Optional[int] = data.get("op")
        t: Optional[str] = data.get("t")
        s: Optional[int] = data.get("s")
        d: Optional[Dict[str, Any]] = data.get("d")

        if s is not None:
            self.sequence = s

        if op == 10:
            self.heartbeat_interval = d["heartbeat_interval"]
            self.logger.success("Hello received, starting heartbeat...")
            self.heartbeat_task = asyncio.create_task(self.send_heartbeat())
            await self.identify()

        elif op == 11:
            self.last_heartbeat_ack = True
            self.logger.info("Heartbeat ACK")

        elif t == "READY":
            self.logger.success(f"Logged in as {d['user']['username']}#{d['user']['discriminator']}")

        elif t == "MESSAGE_CREATE":
            self.logger.info(f"[{d['author']['username']}] {d['content']}")

    def clean_for_json(self, obj: Any) -> Any:
        return self.utils.clean_for_json(obj)

    async def listen(self) -> None:
        try:
            async for message in self.ws:
                debug(f"Received {len(message)} bytes")
                if isinstance(message, bytes):
                    debug(f"First 20 bytes: {message[:20].hex()}")
                    
                    decompressed = await self.decompress_message(message)
                    if not decompressed:
                        self.logger.warning("No decompressed data from this message")
                        continue
                    
                    self.logger.success(f"Decompressed {len(decompressed)} bytes")
                    try:
                        data = erlpack.unpack(decompressed)
                        self.logger.info(f"Event: op={data.get('op')}, t={data.get('t')}")
                        
                        self.logger.info("Decoded payload:")
                        try:
                            clean_data = self.clean_for_json(data)
                            json_str = json.dumps(clean_data, indent=2, ensure_ascii=False)
                            
                            self.logger.info(f"JSON length: {len(json_str)} chars, Event: {data.get('t', 'unknown')}")
                            
                            self.message_count += 1
                            self.utils.handle_large_json(json_str, data.get('t', 'unknown'), self.message_count)
                            
                        except Exception as e:
                            self.logger.error(f"JSON serialization failed: {e}")
                            debug(f"Raw data: {data}")
                        print("─" * 80)
                        
                        await self.handle_message(data)
                    except Exception as e:
                        self.logger.error(f"ETF decode error: {e}")
                        debug(f"Raw data: {decompressed[:100]}...")
                else:
                    self.logger.warning(f"Received non-bytes message: {message}")
        except Exception as e:
            self.logger.error(f"Listen error: {e}")
        finally:
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
                try:
                    await self.heartbeat_task
                except asyncio.CancelledError:
                    pass


def _try_zlib_decompress(chunk: bytes) -> Optional[bytes]:
    for wbits in (15, -15, 47):
        try:
            return zlib.decompress(chunk, wbits=wbits)
        except zlib.error:
            pass
    return None


def decode_har(har_path: str) -> None:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    DIVIDER = "-" * 80

    log.info(f"Decoding HAR file: {har_path}")

    with open(har_path, 'r', encoding='utf-8', errors='replace') as f:
        har = json.load(f)

    os.makedirs("logs", exist_ok=True)
    utils = MiscUtils()
    message_count = 0
    skipped = 0

    entries = har.get('log', {}).get('entries', [])
    for entry in entries:
        ws_messages = entry.get('_webSocketMessages', [])
        if not ws_messages:
            continue

        url = entry.get('request', {}).get('url', '')
        log.info(f"WebSocket entry: {url}")

        zlib_ctx = zlib.decompressobj()

        for msg in ws_messages:
            direction = msg.get('type', 'receive')   # 'send' or 'receive'
            opcode = msg.get('opcode', 1)
            raw = msg.get('data', '')

            if opcode == 1 or direction == 'send':
                # Text frame or client-sent: plain JSON
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    skipped += 1
                    continue
                event_type = data.get('t') or f"op{data.get('op', direction)}"
                message_count += 1
                log.info(f"[{direction}] Message {message_count}: op={data.get('op')}, t={data.get('t')}")
                json_str = json.dumps(data, indent=2, ensure_ascii=False)
                utils.handle_large_json(json_str, event_type, message_count)
                print(DIVIDER)
            else:
                # Binary receive frame: base64-encoded zlib-stream chunk
                try:
                    compressed = base64.b64decode(raw)
                except Exception:
                    skipped += 1
                    continue
                try:
                    decompressed = zlib_ctx.decompress(compressed)
                    data = json.loads(decompressed.decode('utf-8', errors='replace'))
                    event_type = data.get('t') or f"op{data.get('op', 'unknown')}"
                    message_count += 1
                    log.info(f"[{direction}] Message {message_count}: op={data.get('op')}, t={data.get('t')}")
                    json_str = json.dumps(data, indent=2, ensure_ascii=False)
                    utils.handle_large_json(json_str, event_type, message_count)
                    print(DIVIDER)
                except (zlib.error, json.JSONDecodeError):
                    # Streaming context broken; try standalone
                    decompressed = _try_zlib_decompress(compressed)
                    if decompressed:
                        try:
                            data = json.loads(decompressed.decode('utf-8', errors='replace'))
                            event_type = data.get('t') or f"op{data.get('op', 'unknown')}"
                            message_count += 1
                            log.info(f"[{direction}] Message {message_count}: op={data.get('op')}, t={data.get('t')}")
                            json_str = json.dumps(data, indent=2, ensure_ascii=False)
                            utils.handle_large_json(json_str, event_type, message_count)
                            print(DIVIDER)
                        except json.JSONDecodeError:
                            skipped += 1
                    else:
                        skipped += 1

    if skipped:
        log.warning(f"{skipped} frame(s) could not be decoded")
    log.success(f"Decoded {message_count} messages from {har_path}")


def decode_bin(bin_path: str) -> None:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    SEP = b'\n\n---\n\n'
    ZLIB_SUFFIX = b'\x00\x00\xff\xff'
    DIVIDER = "-" * 80

    log.info(f"Decoding bin file: {bin_path}")

    with open(bin_path, 'rb') as f:
        raw_data = f.read()

    os.makedirs("logs", exist_ok=True)
    utils = MiscUtils()
    message_count = 0

    if SEP in raw_data:
        log.info("Detected separator-based format")
        parts = raw_data.split(SEP)
        zlib_ctx = zlib.decompressobj()
        skipped = 0

        for part in parts:
            if not part:
                continue

            # Client-sent messages are plain JSON
            if part.lstrip(b'\x00\x01\x02\x03\x04').startswith(b'{'):
                json_bytes = part.lstrip(b'\x00\x01\x02\x03\x04')
                try:
                    data = json.loads(json_bytes.decode('utf-8', errors='replace'))
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    log.warning(f"JSON parse error: {e}")
                    continue
                event_type = data.get('t') or f"op{data.get('op', 'client')}"
                message_count += 1
                log.info(f"[client] Message {message_count}: op={data.get('op')}, t={data.get('t')}")
                json_str = json.dumps(data, indent=2, ensure_ascii=False)
                utils.handle_large_json(json_str, event_type, message_count)
                print(DIVIDER)
            else:
                # Server-sent binary (zlib-stream); attempt streaming then standalone decompression
                decoded = False
                for decompress_fn in (
                    lambda p: zlib_ctx.decompress(p),
                    lambda p: _try_zlib_decompress(p),
                ):
                    if decoded:
                        break
                    try:
                        decompressed = decompress_fn(part)
                        if not decompressed:
                            continue
                        data = json.loads(decompressed.decode('utf-8', errors='replace'))
                        event_type = data.get('t') or f"op{data.get('op', 'unknown')}"
                        message_count += 1
                        log.info(f"[server] Message {message_count}: op={data.get('op')}, t={data.get('t')}")
                        json_str = json.dumps(data, indent=2, ensure_ascii=False)
                        utils.handle_large_json(json_str, event_type, message_count)
                        print(DIVIDER)
                        decoded = True
                    except (zlib.error, json.JSONDecodeError):
                        pass
                if not decoded:
                    skipped += 1

        if skipped:
            log.warning(f"{skipped} server binary frame(s) could not be decoded (capture tool corrupted the zlib bytes)")
    else:
        # Raw zlib-stream: split on sync-flush markers
        log.info("Detected raw zlib-stream format")
        decompressor = zlib.decompressobj()
        offset = 0
        while offset < len(raw_data):
            end = raw_data.find(ZLIB_SUFFIX, offset)
            if end == -1:
                break
            end += len(ZLIB_SUFFIX)
            chunk = raw_data[offset:end]
            offset = end
            try:
                decompressed = decompressor.decompress(chunk)
            except zlib.error as e:
                log.warning(f"Decompression error at message {message_count + 1}: {e}")
                continue
            if not decompressed:
                continue
            try:
                data = json.loads(decompressed.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                log.warning(f"JSON parse error at message {message_count + 1}: {e}")
                continue
            event_type = data.get('t') or f"op{data.get('op', 'unknown')}"
            message_count += 1
            log.info(f"Message {message_count}: op={data.get('op')}, t={data.get('t')}")
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            utils.handle_large_json(json_str, event_type, message_count)
            print("─" * 80)

    log.success(f"Decoded {message_count} messages from {bin_path}")


async def main() -> None:
    client = DiscordClient(TOKEN)
    await client.connect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discord WebSocket Reader")
    parser.add_argument("--decode-bin", metavar="FILE", help="Decode a captured .bin or .har file")
    args = parser.parse_args()

    if args.decode_bin:
        if args.decode_bin.lower().endswith('.har'):
            decode_har(args.decode_bin)
        else:
            decode_bin(args.decode_bin)
    else:
        asyncio.run(main())