# 파일 경로 및 타입 힌트를 위한 모듈
from pathlib import Path
from typing import List, Dict
import json

# 오디오 저장 및 모델 로딩을 위한 라이브러리
import torch
import soundfile as sf
from diffusers import AudioLDM2Pipeline

# 프롬프트와 도구 등록 유틸
from mm_story_agent.prompts_en import story_to_sound_reviser_system, story_to_sound_review_system
from mm_story_agent.base import register_tool, init_tool_instance

# 오디오 생성기를 구현 클래스
class AudioLDM2Synthesizer:

    def __init__(self,
                 device: str = 'cuda'  # GPU 사용 권장
                 ) -> None:
        self.device = device
        # Hugging Face의 AudioLDM2 모델 불러오기
        self.pipe = AudioLDM2Pipeline.from_pretrained(
            "cvssp/audioldm2",
            torch_dtype=torch.float16  # FP16로 속도/메모리 최적화
        ).to(self.device)

    # 🎧 효과음 생성 함수
    def call(self,
             prompts: List[str],              # 오디오 생성에 사용할 텍스트 목록
             n_candidate_per_text: int = 3,   # 프롬프트당 생성할 오디오 수
             seed: int = 0,                   # 랜덤 시드 고정
             guidance_scale: float = 3.5,     # 텍스트 조건 반영 강도
             ddim_steps: int = 100            # 디퓨전 단계 수
             ):
        # 시드 고정용 생성기
        generator = torch.Generator(device=self.device).manual_seed(seed)

        # 오디오 생성
        audios = self.pipe(
            prompts=prompts,
            num_inference_steps=ddim_steps,
            audio_length_in_s=10.0,
            guidance_scale=guidance_scale,
            generator=generator,
            num_waveforms_per_prompt=n_candidate_per_text
        ).audios

        # 각 프롬프트당 첫 번째 오디오만 선택
        audios = audios[::n_candidate_per_text]
        return audios

# 사운드 에이전트 등록: "audioldm2_t2a" (text-to-audio)
@register_tool("audioldm2_t2a")
class AudioLDM2Agent:

    def __init__(self, cfg) -> None:
        self.cfg = cfg  # 구성 설정 저장

    # 전체 파이프라인 실행 함수
    def call(self, params: Dict):
        pages: List = params["pages"]         # 이야기 페이지 목록
        save_path: str = params["save_path"]  # 오디오 저장 경로

        # 1. 이야기로부터 효과음 설명 생성
        sound_prompts = self.generate_sound_prompt_from_story(pages)

        # 2. 오디오로 생성할 프롬프트만 추림
        save_paths = []
        forward_prompts = []
        save_path = Path(save_path)  # 문자열 → Path 객체
        for idx in range(len(pages)):
            if sound_prompts[idx] != "No sounds.":  # 효과음 필요 없는 경우 제외
                save_paths.append(save_path / f"p{idx + 1}.wav")  # 각 페이지 별 파일명
                forward_prompts.append(sound_prompts[idx])

        # 3. 오디오 생성기 초기화
        generation_agent = AudioLDM2Synthesizer(
            device=self.cfg.get("device", "cuda")
        )

        # 4. 실제 오디오 생성 및 저장
        if len(forward_prompts) > 0:
            sounds = generation_agent.call(
                forward_prompts,
                n_candidate_per_text=params.get("n_candidate_per_text", 3),
                seed=params.get("seed", 0),
                guidance_scale=params.get("guidance_scale", 3.5),
                ddim_steps=params.get("ddim_steps", 100),
            )
            for sound, path in zip(sounds, save_paths):
                # 생성된 오디오를 wav 파일로 저장
                sf.write(path.__str__(), sound, self.cfg["sample_rate"])

        # 결과로 생성된 프롬프트 목록 반환
        return {
            "prompts": sound_prompts,
        }

    # 📘 스토리로부터 효과음 설명 프롬프트 생성
    def generate_sound_prompt_from_story(
            self,
            pages: List,  # 각 페이지는 하나의 텍스트
        ):
        # 설명 생성 LLM 초기화
        sound_prompt_reviser = init_tool_instance({
            "tool": self.cfg.get("llm", "qwen"),
            "cfg": {
                "system_prompt": story_to_sound_reviser_system,
                "track_history": False
            }
        })

        # 설명 검토 LLM 초기화
        sound_prompt_reviewer = init_tool_instance({
            "tool": self.cfg.get("llm", "qwen"),
            "cfg": {
                "system_prompt": story_to_sound_review_system,
                "track_history": False
            }
        })

        num_turns = self.cfg.get("num_turns", 3)  # 반복 횟수 제한
        sound_prompts = []

        # 페이지별 프롬프트 생성
        for page in pages:
            review = ""
            sound_prompt = ""

            # 개선 반복
            for turn in range(num_turns):
                # 1. 설명 생성
                sound_prompt, success = sound_prompt_reviser.call(json.dumps({
                    "story": page,
                    "previous_result": sound_prompt,
                    "improvement_suggestions": review,
                }, ensure_ascii=False))

                # "Sound description:" 접두어 제거
                if sound_prompt.startswith("Sound description:"):
                    sound_prompt = sound_prompt[len("Sound description:"):]

                # 2. 설명 검토
                review, success = sound_prompt_reviewer.call(json.dumps({
                    "story": page,
                    "sound_description": sound_prompt
                }, ensure_ascii=False))

                # 통과하면 반복 종료
                if review == "Check passed.":
                    break

            # 최종 프롬프트 저장
            sound_prompts.append(sound_prompt)

        return sound_prompts
