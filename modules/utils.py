import zstandard as zstd
from typing import Any, Optional
from logmagix import Logger

class MiscUtils:
    def __init__(self):
        self.logger = Logger() 
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
        
        # Always save to file
        if self.save_json_to_file(json_str, filename):
            if len(json_str) > 10000:
                self.logger.info(f"HUGE MESSAGE ({len(json_str)} chars) - showing first 500 chars:")
                print(json_str[:500] + "...")
            elif len(json_str) > 300:
                print(json_str[:300] + "...")
            else:
                print(json_str)
            self.logger.success(f"Full payload saved to: {filename}")
        else:
            # Fallback if file saving fails
            if len(json_str) > 1000:
                self.logger.warning("File save failed, showing truncated JSON (first 1000 chars):")
                print(json_str[:1000] + "...")
            else:
                self.logger.warning("File save failed, showing full JSON:")
                print(json_str)
        
        return filename
