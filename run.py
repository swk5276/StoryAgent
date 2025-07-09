# import argparse
# import yaml
# from mm_story_agent import MMStoryAgent
# from mm_story_agent import mm_story_agent  # RefineWriterAgent 등 포함된 파일

# from mm_story_agent.prompts_en2 import (
#     refine_writer_system,
#     scene_extractor_system,
#     summary_writer_system,
#     meta_writer_system,
# )

# #  실행 명령어 python run.py -c configs/mm_story_agent.yaml


# # 명령 줄 인자로 .yaml 설정파일을 받아서, 해당 설정을 기반으로 MMStoryAgent 객체를 생성하고 .call(config)를 실행
# if __name__ == "__main__":
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--config", "-c", type=str, required=True) # 설정 파일 경로 지정
#     args = parser.parse_args()

#     with open(args.config, encoding='utf-8') as reader:
#         config = yaml.load(reader, Loader=yaml.FullLoader) # yaml으로 설정 파일 로드

#     # ✅ 각 에이전트에 system_prompt 주입
#     config["refine_writer"]["cfg"]["system_prompt"] = refine_writer_system
#     config["scene_extractor"]["cfg"]["system_prompt"] = scene_extractor_system
#     config["summary_writer"]["cfg"]["system_prompt"] = summary_writer_system
#     config["meta_writer"]["cfg"]["system_prompt"] = meta_writer_system

#     mm_story_agent = MMStoryAgent() #MMStoryAgent 클래스를 import 하여 실행
#     # mm_story_agent.call(config) # 기존 로직
#     mm_story_agent.run_text_scene_pipeline(config)  # 새 로직 실행

import argparse
import yaml
from mm_story_agent import MMStoryAgent
from mm_story_agent import mm_story_agent  # RefineWriterAgent 등 포함된 파일

from mm_story_agent.prompts_en2 import (
    refine_writer_system,
    summary_writer_system,
    meta_writer_system,
)

# 실행 명령어 예시:
# python run.py -c configs/mm_story_agent.yaml

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", "-c", type=str, required=True)  # 설정 파일 경로 지정
    args = parser.parse_args()

    with open(args.config, encoding='utf-8') as reader:
        config = yaml.load(reader, Loader=yaml.FullLoader)

    # system_prompt 주입 (SceneExtractorAgent는 내부적으로 system_prompt 3개 구성 → 따로 주입하지 않음)
    config["refine_writer"]["cfg"]["system_prompt"] = refine_writer_system
    config["summary_writer"]["cfg"]["system_prompt"] = summary_writer_system
    config["meta_writer"]["cfg"]["system_prompt"] = meta_writer_system

    mm_story_agent = MMStoryAgent()
    mm_story_agent.run_text_scene_pipeline(config)  # 새 로직 실행
