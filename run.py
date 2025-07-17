# Agent 진입점
# 주요 목적: YAML 설정 파일을 받아, 여러 스토리 에이전트 구성 요소에 system prompt를 주입한 뒤
# MMStoryAgent의 run_text_scene_pipeline() 메서드를 실행하여 전체 스토리 파이프라인을 작동시킴.

import argparse # config 파일을 받을 수 있도록 해줌
import yaml # yaml(설정파일)을 읽고 딕셔너리로 파싱
import os

from mm_story_agent import MMStoryAgent # 멀티 모달 스토리 에이전트 핵심 클래스
from mm_story_agent.modality_agents import story_agent  # 여러 Agent가 포함된 모듈
from mm_story_agent.modality_agents.whisper_utils import transcribe_audio

from mm_story_agent.prompts_en2 import (
    refine_writer_system,
    summary_writer_system,
    meta_writer_system,
)

# python run.py -c configs/mm_story_agent.yaml -a data/audio/my_voice.wav

# python run.py -c configs/mm_story_agent.yaml -a data/b.mp3


def inject_whisper_text_to_config(config, whisper_text: str):
    # full_context 필드가 story_writer.params 아래에 있는지 확인하고 삽입
    if "story_writer" not in config:
        config["story_writer"] = {}
    if "params" not in config["story_writer"]:
        config["story_writer"]["params"] = {}
    config["story_writer"]["params"]["full_context"] = whisper_text
    print("[INFO] Whisper 텍스트가 story_writer.params.full_context에 삽입되었습니다.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", "-c", type=str, required=True, help="YAML 설정 파일 경로")
    parser.add_argument("--audio", "-a", type=str, required=False, help="Whisper용 음성 파일 경로")
    args = parser.parse_args()

    # 설정 로딩
    with open(args.config, encoding='utf-8') as reader:
        config = yaml.load(reader, Loader=yaml.FullLoader)

    # Whisper 실행 및 결과 삽입
    if args.audio:
        print(f"[INFO] Whisper로 음성 인식 중... ({args.audio})")
        whisper_text = transcribe_audio(args.audio)
        print(f"[INFO] 추출된 텍스트:\n{whisper_text[:200]}...\n")
        
        inject_whisper_text_to_config(config, whisper_text)

        # 옵션: 전체 텍스트를 파일로 저장
        story_dir = config.get("video_compose", {}).get("params", {}).get("story_dir", "generated_stories/example")
        os.makedirs(story_dir, exist_ok=True)
        with open(os.path.join(story_dir, "full_text.txt"), "w", encoding="utf-8") as f:
            f.write(whisper_text)

    # 시스템 프롬프트 주입
    config["refine_writer"]["cfg"]["system_prompt"] = refine_writer_system
    config["summary_writer"]["cfg"]["system_prompt"] = summary_writer_system
    config["meta_writer"]["cfg"]["system_prompt"] = meta_writer_system

    # 전체 스토리 생성 파이프라인 실행
    mm_story_agent = MMStoryAgent()
    mm_story_agent.call(config)
