import argparse
import yaml
from mm_story_agent import MMStoryAgent
#  실행 명령어 python run.py -c configs/mm_story_agent.yaml
# 명령 줄 인자로 .yaml 설정파일을 받아서, 해당 설정을 기반으로 MMStoryAgent 객체를 생성하고 .call(config)를 실행
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", "-c", type=str, required=True) # 설정 파일 경로 지정
    args = parser.parse_args()

    with open(args.config, encoding='utf-8') as reader:
        config = yaml.load(reader, Loader=yaml.FullLoader) # yaml으로 설정 파일 로드

    mm_story_agent = MMStoryAgent() #MMStoryAgent 클래스를 import 하여 실행
    mm_story_agent.call(config)
