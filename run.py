import argparse # config 파일을 받을 수 있도록 해줌
import yaml # yaml(설정파일)을 읽고 딕셔너리로 파싱
import os
from mm_story_agent import MMStoryAgent # 멀티 모달 스토리 에이전트 핵심 클래스
from mm_story_agent.modality_agents import story_agent  # 여러 Agent가 포함된 모듈
from mm_story_agent.modality_agents.whisper_utils import (
    transcribe_and_save_all_models,
    summarize_and_save_final_text,
    inject_whisper_text_to_config
)
from mm_story_agent.prompts_en2 import (
    refine_writer_system,
    summary_writer_system,
    meta_writer_system,
    scene_refined_output_system
)
from pathlib import Path
from mm_story_agent.modality_agents.LLMexaone import ExaoneAgent


### 코드 실행 명령어
# python run.py -c configs/mm_story_agent.yaml -a data/이상윤.mp3


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # 인자들을 통해 YAML 설정 파일 경로와 음성파일 경로 받기
    parser.add_argument("--config", "-c", type=str, required=True, help="YAML 설정 파일 경로")
    parser.add_argument("--audio", "-a", type=str, required=False, help="Whisper용 음성 파일 경로")
    args = parser.parse_args()

    # YAML 설정 파일 불러오기
    with open(args.config, encoding='utf-8') as reader:
        config = yaml.load(reader, Loader=yaml.FullLoader)

    # story 디렉토리 생성
    story_dir = config.get("video_compose", {}).get("params", {}).get("story_dir", "generated_stories/example")
    os.makedirs(story_dir, exist_ok=True)
    # Whisper 음성 인식 수행
    if args.audio:
        print(f"[INFO] Whisper 다중 모델 음성 인식 수행 중... ({args.audio})")
        whisper_texts = transcribe_and_save_all_models(args.audio, story_dir)

        # LLM Agent 생성
        llm_agent = ExaoneAgent(config)

        # 다중 결과 통합
        final_text = summarize_and_save_final_text(whisper_texts, story_dir, llm_agent)

        # 최종 텍스트를 config에 삽입
        inject_whisper_text_to_config(config, final_text)

    else:
        # Whisper 없이 실행할 경우: full_text_raw.txt가 존재해야 함
        raw_text_path = Path(story_dir) / "full_text_raw.txt"
        if not raw_text_path.exists():
            raise FileNotFoundError(f"{raw_text_path} 파일이 존재하지 않습니다. Whisper 없이 실행하려면 이 파일이 필요합니다.")
        with open(raw_text_path, encoding='utf-8') as f:
            raw_text = f.read()
        inject_whisper_text_to_config(config, raw_text)


    # 임시로 바로 넘겨주기 위해서 사용
    # python run.py -c configs/mm_story_agent.yaml
    # story_dir = config.get("video_compose", {}).get("params", {}).get("story_dir", "generated_stories/example")
    # os.makedirs(story_dir, exist_ok=True)

    # raw_text_path = Path(story_dir) / "full_text_raw.txt"
    # if not raw_text_path.exists():
    #     raise FileNotFoundError(f"{raw_text_path} 파일이 존재하지 않습니다. Whisper 없이 실행하려면 이 파일이 필요합니다.")

    # with open(raw_text_path, encoding='utf-8') as f:
    #     raw_text = f.read()

    # # config에 삽입
    # if "story_writer" not in config:
    #     config["story_writer"] = {}
    # if "params" not in config["story_writer"]:
    #     config["story_writer"]["params"] = {}
    # config["story_writer"]["params"]["full_context"] = raw_text
    # print("[INFO] full_text_raw.txt에서 텍스트를 불러와 story_writer.params.full_context에 삽입했습니다.")

    # 시스템 프롬프트 주입
    config["refine_writer"]["cfg"]["system_prompt"] = refine_writer_system
    config["summary_writer"]["cfg"]["system_prompt"] = summary_writer_system
    config["scene_extractor"]["cfg"]["system_prompt"] = scene_refined_output_system
    config["meta_writer"]["cfg"]["system_prompt"] = meta_writer_system

    # 전체 스토리 생성 파이프라인 실행
    mm_story_agent = MMStoryAgent()
    mm_story_agent.call(config)