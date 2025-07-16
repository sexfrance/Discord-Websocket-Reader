import asyncio
import websockets
import zstandard as zstd
import erlpack
import json
import os
import toml

from logmagix import Logger
from functools import wraps
from typing import Dict, Any, Optional

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

class MiscUtils:
    def __init__(self):
        self.logger = log
        self.zstd_decompressor = zstd.ZstdDecompressor()
        self.zstd_context = self.zstd_decompressor.decompressobj()
        
    def clean_for_json(self, obj: Any) -> Any:
        if isinstance(obj, bytes):
            try:
                return obj.decode('utf-8')
            except:
                return f"<bytes: {obj.hex()}>"
        elif hasattr(obj, '__class__') and obj.__class__.__name__ == 'Atom':
            return str(obj).replace('Atom(', '').replace(')', '')
        elif isinstance(obj, dict):
            return {self.clean_for_json(k): self.clean_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.clean_for_json(item) for item in obj]
        elif isinstance(obj, tuple):
            return [self.clean_for_json(item) for item in obj]
        else:
            return obj
    
    def decompress_message(self, message: bytes) -> Optional[bytes]:
        try:
            decompressed = self.zstd_context.decompress(message)
            if decompressed:
                return decompressed
            else:
                return None
        except Exception as e:
            self.logger.warning(f"Streaming decompression error: {e}")
            try:
                self.zstd_context = self.zstd_decompressor.decompressobj()
                decompressed = self.zstd_context.decompress(message)
                return decompressed
            except:
                self.logger.warning("Reset failed, trying direct decompression")
                try:
                    return self.zstd_decompressor.decompress(message)
                except:
                    return None
    
    def save_json_to_file(self, json_str: str, filename: str) -> bool:
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(json_str)
            return True
        except Exception as e:
            self.logger.error(f"Failed to save JSON to {filename}: {e}")
            return False
    
    def handle_large_json(self, json_str: str, event_type: str, message_count: int) -> str:
        filename = f"logs/message_{message_count:04d}_{event_type}.json"
        
        if len(json_str) > 10000:
            if self.save_json_to_file(json_str, filename):
                self.logger.info(f"HUGE MESSAGE ({len(json_str)} chars) - showing first 500 chars:")
                print(json_str[:500] + "...")
                self.logger.success(f"Full payload saved to: {filename}")
            else:
                self.logger.warning("Showing truncated JSON instead (first 1000 chars):")
                print(json_str[:1000] + "...")
        elif len(json_str) > 300:
            if self.save_json_to_file(json_str, filename):
                print(json_str[:300] + "...")
                self.logger.success(f"Full payload saved to: {filename}")
            else:
                self.logger.warning("Showing full JSON instead:")
                print(json_str)
        else:
            print(json_str)
        
        return filename

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


async def main() -> None:
    client = DiscordClient(TOKEN)
    await client.connect()

if __name__ == "__main__":
    asyncio.run(main())