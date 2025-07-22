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

# voice to text injection function
def inject_whisper_text_to_config(config, whisper_text: str):
    # full_context field
    if "story_writer" not in config:
        config["story_writer"] = {}
    if "params" not in config["story_writer"]:
        config["story_writer"]["params"] = {}
    config["story_writer"]["params"]["full_context"] = whisper_text
    print("[INFO] Whisper 텍스트가 story_writer.params.full_context에 삽입되었습니다.")


#################### 코드 실행 명령어 #####################
# python run.py -c configs/mm_story_agent.yaml -a data/이상윤.mp3

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # 인자들을 통해 YAML 설정 파일 경로와 음성파일 경로 받기 (실행 명령어를 통해)
    parser.add_argument("--config", "-c", type=str, required=True, help="YAML 설정 파일 경로")
    parser.add_argument("--audio", "-a", type=str, required=False, help="Whisper용 음성 파일 경로")
    args = parser.parse_args()

    # config 변수에 YAML 설정 파일 내용 파싱하여 저장
    with open(args.config, encoding='utf-8') as reader:
        config = yaml.load(reader, Loader=yaml.FullLoader)

    # Whisper [ voice data => text data ]
    if args.audio:
        print(f"[INFO] Whisper로 음성 인식 중... ({args.audio})")
        whisper_text = transcribe_audio(args.audio)
        print(f"[INFO] 추출된 텍스트:\n{whisper_text[:200]}...\n")
        
        inject_whisper_text_to_config(config, whisper_text) # 변환된 텍스트를 config 내 스토리 관련 항목에 삽입합니다.

        story_dir = config.get("video_compose", {}).get("params", {}).get("story_dir", "generated_stories/example")
        os.makedirs(story_dir, exist_ok=True)

    # 시스템 프롬프트 주입
    config["refine_writer"]["cfg"]["system_prompt"] = refine_writer_system
    config["summary_writer"]["cfg"]["system_prompt"] = summary_writer_system
    config["meta_writer"]["cfg"]["system_prompt"] = meta_writer_system

    # 전체 스토리 생성 파이프라인 실행
    mm_story_agent = MMStoryAgent()
    mm_story_agent.call(config)