import time
import json
from pathlib import Path
import sys
from networkx import full_rary_tree
import torch.multiprocessing as mp
mp.set_start_method("spawn", force=True)
import ast
from tqdm import tqdm
from tqdm import trange
from .base import init_tool_instance

class MMStoryAgent:

    def __init__(self) -> None:
        # 사용할 모달리티 목록 지정 ("speech", "music")
        self.modalities = ["image","speech", "music"]

    def call_modality_agent(self, modality, agent, params, return_dict):
        # 에이전트의 call 메서드로 결과 생성
        result = agent.call(params)
        # 결과를 공유 딕셔너리에 저장
        return_dict[modality] = result
    
    def generate_modality_assets(self, config, scene_summaries, scene_metadatas):
        story_dir = Path(config["story_dir"])
        for sub_dir in self.modalities:
            (story_dir / sub_dir).mkdir(exist_ok=True, parents=True)

        agents = {}
        params = {}
        processes = []
        return_dict = mp.Manager().dict()

        for modality in self.modalities:
            agents[modality] = init_tool_instance(config[modality + "_generation"])
            
            # 모달리티별로 페이지 소스 다르게 선택
            if modality == "image":
                page_data = scene_metadatas
            else:
                page_data = scene_summaries

            params[modality] = config[modality + "_generation"]["params"].copy()

            params[modality].update({
                "pages": page_data,
                "save_path": story_dir / modality
            })

            p = mp.Process(
                target=self.call_modality_agent,
                args=(modality, agents[modality], params[modality], return_dict)
            )
            processes.append(p)
            p.start()

        for p in processes:
            p.join()

        print("모달리티별 자산 생성 완료.")

    def compose_storytelling_video(self, config, scene_summaries, scene_metadatas, use_metadata_for_video=False):
        # 비디오 합성용 에이전트 초기화
        video_compose_agent = init_tool_instance(config["video_compose"])

        # 페이지 데이터 선택
        pages = scene_metadatas if use_metadata_for_video else scene_summaries

        # 파라미터 복사 후 페이지 정보 추가
        params = config["video_compose"]["params"].copy()
        params["pages"] = pages

        # 비디오 합성 실행
        video_compose_agent.call(params)

    # total 
    def call(self, config):

        # 파일 경로 객체
        story_dir = Path(config["story_dir"])

        # Whisper text in params
        raw_text = config["story_writer"]["params"]["full_context"]

        with open(story_dir / "full_text_raw.txt", "w", encoding="utf-8") as f:
            f.write(raw_text)


        # Refine writer [ full_text_raw => full_text ]
        refine_writer = init_tool_instance(config["refine_writer"])
        full_text = refine_writer.call({"raw_text": raw_text})

        with open(story_dir / "full_text.txt", "w", encoding="utf-8") as f:
            f.write(full_text)


        # Scene extractor [ full_text => scene_text ]
        scene_extractor = init_tool_instance(config["scene_extractor"])
        scene_list = scene_extractor.call({"full_text": full_text})

        with open(story_dir / "scene_text.json", "w", encoding="utf-8") as f:
            json.dump({"scenes": scene_list}, f, indent=4, ensure_ascii=False)


        # Scene narration & scripter [ scene_text => scene_summaries ]
        summary_writer = init_tool_instance(config["summary_writer"])
        scene_summaries = []

        meta_writer = init_tool_instance(config["meta_writer"])
        scene_metadatas = []

        print("Scene별 대본, 메타, 등장인물 생성 중...")


        for idx, scene in enumerate(tqdm(scene_list, desc="Generating summary/metadata per scene")):

            try:
                raw_summary = summary_writer.call({"scene_text": scene})  # 문자열 형태의 JSON이 올 수 있음

                try:
                    parsed = json.loads(raw_summary)  # 문자열 -> dict
                    summary = parsed["scenes"][0]["summary"]  # summary만 추출
                except Exception:
                    summary = raw_summary  # JSON 구조가 아니면 원본 그대로 저장

            except Exception as e:
                summary = f"[Error generating summary]: {e}"

            scene_summaries.append(summary)
            # try:
            #     summary = summary_writer.call({"scene_text": scene})
            # except Exception as e:
            #     summary = f"[Error generating summary]: {e}"
            # scene_summaries.append(summary)

            try:
                metadata = meta_writer.call({"scene_text": scene})
            except Exception as e:
                metadata = f"[Error generating metadata]: {e}"
            scene_metadatas.append(metadata)

        # Saving summary & metadata 
        with open(story_dir / "scene_summaries.json", "w", encoding="utf-8") as f:
            json.dump(scene_summaries, f, ensure_ascii=False, indent=2)

        with open(story_dir / "scene_metadatas.json", "w", encoding="utf-8") as f:
            json.dump(scene_metadatas, f, ensure_ascii=False, indent=2)

        print("Text-to-Scene pipeline completed.")

        return
    
        # Generating modality
        print("Generating modality assets...")
        pages = [s for s in scene_summaries]  # 요약 결과를 각 페이지 story로 활용
        self.generate_modality_assets(config, scene_summaries, scene_metadatas)
        # 5. 비디오 합성
        print("🎬 Composing storytelling video...")
        self.compose_storytelling_video(
            config,
            scene_summaries=scene_summaries,
            scene_metadatas=scene_metadatas,
            use_metadata_for_video=False  # ← 필요 시 True로 변경
        )

