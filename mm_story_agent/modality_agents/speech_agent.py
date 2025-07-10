import os
import asyncio
import edge_tts
from pathlib import Path
from typing import List, Dict
from mm_story_agent.base import register_tool

# 마이크로소프트의 엣지의 TTS(음성 합성) API인 edget_tts를 활용하여 텍스트 페이지들을 음성 파일로 저장하는 기능을 수행합니다.
# 전체 구조는 2개의 클래스로 나뉘며, @register_tool("cosyvoice_tts")를 통해 에이전트 시스템에 등록

# 실제 TTS 합성을 수행하는 비동기 음성 합성 도구 클래스
class EdgeTTSSynthesizer:
    # 한국어 음성 설정
    def __init__(self) -> None:
        self.default_voice = "ko-KR-SunHiNeural"
    
    # 주어진 Text, voice로 TTS 수행후 output_file에 저장
    async def synthesize_async(self, text: str, voice: str, output_file: str):
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)
    
    # 런타임에 따른 적절한 비동기 처리 (여러 음성 병렬 처리)
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
        
# 여러 페이지 텍스트를 순차적으로 음성 파일로 생성하는 에이전트 클래스 ( 내부에서 TTS 실행을 위해 EdgeTTSSynthesizer을 호출)
@register_tool("cosyvoice_tts")
class CosyVoiceAgent:
    # 설정파일이나 dictionary 객체를 저장
    def __init__(self, cfg) -> None:
        self.cfg = cfg
    
    # 각 페이지별 텍스트 리스트와 음성 파일을 저장할 경로
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
        # 스피치 반환
        return {
            "modality": "speech"
        }
