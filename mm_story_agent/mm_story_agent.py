# 시간 관련 기능을 위한 모듈
import time
# JSON 파일 저장 및 로드를 위한 모듈
import json
# 경로 처리를 위한 pathlib 모듈
from pathlib import Path
# 시스템 관련 기능을 위한 모듈
import sys
# PyTorch의 멀티프로세싱 기능을 사용하기 위한 모듈
from networkx import full_rary_tree
import torch.multiprocessing as mp
# 멀티프로세싱 방식 설정 (spawn 방식으로 강제 설정)
mp.set_start_method("spawn", force=True)
import ast
from tqdm import tqdm
from tqdm import trange
# 사용자 정의 도구 인스턴스를 초기화하는 함수 불러오기
from .base import init_tool_instance

# 멀티모달 스토리 에이전트를 정의하는 클래스
class MMStoryAgent:

    # 클래스 생성자
    def __init__(self) -> None:
        # 사용할 모달리티 목록 지정 ("speech", "music")
        self.modalities = ["speech", "music"]

    # 모달리티 에이전트를 별도의 프로세스에서 호출하는 함수
    def call_modality_agent(self, modality, agent, params, return_dict):
        # 에이전트의 call 메서드로 결과 생성
        result = agent.call(params)
        # 결과를 공유 딕셔너리에 저장
        return_dict[modality] = result

    # 스토리 작성 함수
    def write_story(self, config):
        # yaml 설정에서 스토리 작성 관련 부분 추출
        cfg = config["story_writer"]
        # 스토리 작성용 에이전트 초기화
        story_writer = init_tool_instance(cfg)
        # 스토리 작성 실행 => 여러 페이지가 생성됨
        pages = story_writer.call(cfg["params"])
        # 생성된 페이지 반환
        return pages
    
    # 음성/음악 등 모달리티 자산을 생성하는 함수
    def generate_modality_assets(self, config, pages):
        # 스토리 데이터 구조 초기화 (각 페이지는 story만 담고 있음)
        script_data = {"pages": [{"story": page} for page in pages]}
        # 저장할 디렉토리 경로 설정
        story_dir = Path(config["story_dir"])

        # 모달리티별 저장 폴더 생성 (존재하지 않으면 생성)
        for sub_dir in self.modalities:
            (story_dir / sub_dir).mkdir(exist_ok=True, parents=True)

        # 에이전트 및 파라미터 저장용 딕셔너리 초기화
        agents = {}
        params = {}
        for modality in self.modalities:
            # 해당 모달리티에 사용할 에이전트 초기화
            agents[modality] = init_tool_instance(config[modality + "_generation"])
            # 설정에서 파라미터 복사 후 pages 및 save_path 추가
            params[modality] = config[modality + "_generation"]["params"].copy()
            params[modality].update({
                "pages": pages,
                "save_path": story_dir / modality
            })

        # 멀티프로세싱을 위한 프로세스 리스트 및 결과 저장용 딕셔너리 초기화
        processes = []
        return_dict = mp.Manager().dict()

        # 각 모달리티에 대해 별도 프로세스 실행
        for modality in self.modalities:
            p = mp.Process(
                target=self.call_modality_agent,  # 실행할 함수
                args=(  # 함수에 전달할 인자
                    modality,
                    agents[modality],
                    params[modality],
                    return_dict)
                )
            processes.append(p)  # 프로세스 리스트에 추가
            p.start()  # 프로세스 실행
        
        # 모든 프로세스가 종료될 때까지 대기
        for p in processes:
            p.join()

        # 결과 처리
        for modality, result in return_dict.items():
            try:
                # 이미지 모달리티가 있는 경우 예외 처리용 주석 (현재는 사용 안 함)
                # if modality == "image":
                #     images = result["generation_results"]
                #     for idx in range(len(pages)):
                #         script_data["pages"][idx]["image_prompt"] = result["prompts"][idx]
                
                # 사운드 모달리티의 경우 각 페이지에 sound_prompt 추가
                if modality == "sound":
                    for idx in range(len(pages)):
                        script_data["pages"][idx]["sound_prompt"] = result["prompts"][idx]
                # 음악 모달리티의 경우 전체 prompt만 저장
                elif modality == "music":
                    script_data["music_prompt"] = result["prompt"]
            except Exception as e:
                # 예외 발생 시 에러 메시지 출력
                print(f"Error occurred during generation: {e}")
        
        # 최종 script_data를 JSON 파일로 저장
        with open(story_dir / "script_data.json", "w") as writer:
            json.dump(script_data, writer, ensure_ascii=False, indent=4)
        
        # 반환 없음
        return None
    # 비디오 합성을 위한 함수
    def compose_storytelling_video(self, config, pages):
        # 비디오 합성용 에이전트 초기화
        video_compose_agent = init_tool_instance(config["video_compose"])
        # 파라미터 복사 후 페이지 정보 추가
        params = config["video_compose"]["params"].copy()
        params["pages"] = pages
        # 비디오 합성 실행
        video_compose_agent.call(params)

    # 전체 파이프라인 실행 함수 
    def call(self, config):
        from pathlib import Path
        import json

        # 디렉토리 생성
        story_dir = Path(config["story_dir"])
        story_dir.mkdir(parents=True, exist_ok=True)

        # Whisper 결과 입력 받기
        raw_text = config["story_writer"]["params"]["full_context"]

        # 1. Whisper 결과 원본 저장
        with open(story_dir / "full_text_raw.txt", "w", encoding="utf-8") as f:
            f.write(raw_text)

        # 2. 정제 처리
        refine_writer = init_tool_instance(config["refine_writer"])
        full_text = refine_writer.call({"raw_text": raw_text})

        # 3. 정제된 텍스트 저장
        with open(story_dir / "full_text.txt", "w", encoding="utf-8") as f:
            f.write(full_text)


        # 2. 신(scene) 분리
        scene_extractor = init_tool_instance(config["scene_extractor"])
        scene_list = scene_extractor.call({"full_text": full_text})
        with open(story_dir / "scene_text.json", "w", encoding="utf-8") as f:
            json.dump({"scenes": scene_list}, f, indent=4, ensure_ascii=False)

        # 3. Scene별 요약 및 메타데이터
        summary_writer = init_tool_instance(config["summary_writer"])
        meta_writer = init_tool_instance(config["meta_writer"])

        scene_summaries = []
        scene_metadatas = []

        print("📚 Scene별 요약 및 메타데이터 생성 중...")

        for idx, scene in enumerate(tqdm(scene_list, desc="▶ Generating summary/metadata per scene")):
            try:
                summary = summary_writer.call({"scene_text": scene})
            except Exception as e:
                summary = f"[Error generating summary]: {e}"
            scene_summaries.append(summary)

            try:
                metadata = meta_writer.call({"scene_text": scene})
            except Exception as e:
                metadata = f"[Error generating metadata]: {e}"
            scene_metadatas.append(metadata)

        # 저장
        with open(story_dir / "scene_summaries.json", "w", encoding="utf-8") as f:
            json.dump(scene_summaries, f, indent=4, ensure_ascii=False)

        with open(story_dir / "scene_metadatas.json", "w", encoding="utf-8") as f:
            json.dump(scene_metadatas, f, indent=4, ensure_ascii=False)

        print("✅ Text-to-Scene pipeline completed.")

        return
        # 4. 모달리티 자산 생성
        print("🎵 Generating modality assets...")
        pages = [s for s in scene_summaries]  # 요약 결과를 각 페이지 story로 활용
        self.generate_modality_assets(config, pages)
        # 5. 비디오 합성
        print("🎬 Composing storytelling video...")
        self.compose_storytelling_video(config, pages)

