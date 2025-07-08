# 파일 경로를 위한 모듈
from pathlib import Path
# JSON 데이터 직렬화/역직렬화를 위한 모듈
import json
# 타입 힌트를 위한 모듈들
from typing import List, Union, Dict

# 오디오 저장을 위한 라이브러리
import soundfile as sf
# 오디오 리샘플링을 위한 라이브러리
import torchaudio
# Hugging Face MusicGen 모델 관련 모듈
from transformers import AutoProcessor, MusicgenForConditionalGeneration

# 음악 생성 관련 시스템 프롬프트 (스토리 → 음악 프롬프트 생성 및 리뷰용)
from mm_story_agent.prompts_en import story_to_music_reviser_system, story_to_music_reviewer_system
# 도구 등록과 초기화 유틸리티
from mm_story_agent.base import register_tool, init_tool_instance


# Hugging Face의 MusicGen을 활용한 실제 음악 생성기 클래스
class MusicGenSynthesizer:

    def __init__(self,
                 model_name: str = 'facebook/musicgen-medium',  # 기본 모델
                 device: str = 'cuda',                          # 디바이스 설정 (GPU 권장)
                 sample_rate: int = 16000                       # 출력 오디오 샘플레이트
                 ) -> None:
        self.device = device
        self.sample_rate = sample_rate

        # 입력 텍스트를 모델 입력 형식으로 처리하는 프로세서
        self.processor = AutoProcessor.from_pretrained(model_name)

        # MusicGen 모델 로드 및 디바이스 이동
        self.model = MusicgenForConditionalGeneration.from_pretrained(model_name).to(device)

    # 텍스트 프롬프트를 받아 음악을 생성하고 .wav 파일로 저장
    def call(self,
             prompt: Union[str, List[str]],
             save_path: Union[str, Path],
             duration: float = 30.0,  # 생성할 오디오 길이 (초 단위)
             ):
        # 텍스트 프롬프트 전처리
        inputs = self.processor(
            text=[prompt],
            padding=True,
            return_tensors="pt",  # 파이토치 텐서 반환
        ).to(self.device)

        # 생성할 토큰 수 계산 (초 단위 → 모델 기준 길이로 변환)
        seq_length = int(51.2 * duration)

        # 오디오 생성 (1개만 생성됨)
        wav = self.model.generate(**inputs, max_new_tokens=seq_length)[0, 0].cpu()

        # 생성된 오디오를 지정된 샘플레이트로 리샘플링
        wav = torchaudio.functional.resample(
            wav,
            orig_freq=self.model.config.audio_encoder.sampling_rate,
            new_freq=self.sample_rate
        )

        # .wav 파일로 저장
        sf.write(save_path, wav.numpy(), self.sample_rate)


# ✅ 에이전트 등록: "musicgen_t2m"이라는 이름으로 외부에서 호출 가능
@register_tool("musicgen_t2m")
class MusicGenAgent:

    # 에이전트 초기화
    def __init__(self, cfg) -> None:
        self.cfg = cfg  # 설정 저장

    # 📌 이야기 페이지들을 기반으로 음악 설명 프롬프트를 생성하는 함수
    def generate_music_prompt_from_story(self, pages: List):
        # 음악 설명을 생성하는 LLM 인스턴스 초기화 (reviser 역할)
        music_prompt_reviser = init_tool_instance({
            "tool": self.cfg.get("llm", "qwen"),  # 기본은 qwen
            "cfg": {
                "system_prompt": story_to_music_reviser_system,
                "track_history": False
            }
        })

        # 생성된 설명을 검토하는 LLM 인스턴스 초기화 (reviewer 역할)
        music_prompt_reviewer = init_tool_instance({
            "tool": self.cfg.get("llm", "qwen"),
            "cfg": {
                "system_prompt": story_to_music_reviewer_system,
                "track_history": False
            }
        })

        music_prompt = ""  # 초기 프롬프트
        review = ""        # 리뷰 내용 초기화

        # 최대 N회까지 프롬프트 개선 반복
        for turn in range(self.cfg.get("max_turns", 3)):
            # 프롬프트 생성 (이야기 + 이전 결과 + 개선 제안)
            music_prompt, success = music_prompt_reviser.call(json.dumps({
                "story": pages,
                "previous_result": music_prompt,
                "improvement_suggestions": review,
            }, ensure_ascii=False))

            # 생성된 프롬프트에 대해 리뷰 요청
            review, success = music_prompt_reviewer.call(json.dumps({
                "story_content": pages,
                "music_description": music_prompt
            }, ensure_ascii=False))

            # 리뷰 결과가 "통과"이면 반복 종료
            if review == "Check passed.":
                break
        
        return music_prompt  # 최종 프롬프트 반환

    # 🎵 전체 음악 생성 파이프라인 실행 함수
    def call(self, params: Dict):
        # 입력 파라미터 추출
        pages: List = params["pages"]          # 이야기 페이지들
        save_path: str = params["save_path"]   # 저장할 경로
        save_path = Path(save_path)            # 문자열을 Path 객체로 변환

        # 1. 이야기로부터 음악 프롬프트 생성
        music_prompt = self.generate_music_prompt_from_story(pages)

        # 2. MusicGen 기반 음악 생성기 초기화
        generation_agent = MusicGenSynthesizer(
            model_name=self.cfg.get("model_name", "facebook/musicgen-medium"),
            device=self.cfg.get("device", "cuda"),
            sample_rate=self.cfg.get("sample_rate", 16000),
        )

        # 3. 생성된 프롬프트를 이용해 음악 생성 및 저장
        generation_agent.call(
            prompt=music_prompt,
            save_path=save_path / "music.wav",  # music.wav로 저장
            duration=params.get("duration", 30.0),  # 생성 길이
        )

        # 생성된 프롬프트를 반환 (결과 확인용)
        return {
            "prompt": music_prompt,
        }