import os
import asyncio
import edge_tts
from pathlib import Path
from typing import List, Dict
from mm_story_agent.base import register_tool

class EdgeTTSSynthesizer:
    def __init__(self) -> None:
        self.default_voice = "ko-KR-SunHiNeural"
    
    async def synthesize_async(self, text: str, voice: str, output_file: str):
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)
    
    def call(self, save_file, transcript, voice="ko-KR-SunHiNeural", sample_rate=16000):
        os.makedirs(os.path.dirname(save_file), exist_ok=True)
        voice = voice or self.default_voice
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.synthesize_async(transcript, voice, save_file))
            else:
                loop.run_until_complete(self.synthesize_async(transcript, voice, save_file))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.synthesize_async(transcript, voice, save_file))
        

@register_tool("cosyvoice_tts")
class CosyVoiceAgent:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
    
    def call(self, params: Dict):
        pages: List = params["pages"]
        save_path: str = params["save_path"]
        generation_agent = EdgeTTSSynthesizer()
        
        for idx, page in enumerate(pages):
            generation_agent.call(
                save_file=save_path / f"p{idx + 1}.wav",
                transcript=page,
                voice=params.get("voice", "ko-KR-SunHiNeural"),
                sample_rate=self.cfg.get("sample_rate", 16000)
            )
        
        return {
            "modality": "speech"
        }
