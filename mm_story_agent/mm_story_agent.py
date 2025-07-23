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

# 스토리 에이전트 제어
class MMStoryAgent:

    def __init__(self) -> None:
        # 사용할 모달리티 목록 지정 ("speech", "music")
        self.modalities = ["image","speech", "music"]

    # 전체 파이프 라인
    def call(self, config):
        # 디렉토리 설정 및 생성
        story_dir = self._get_story_dir(config)
        raw_text = self._get_raw_text(config)

        self._write_file(story_dir / "full_text_raw.txt", raw_text)

        full_text = self._refine_text(config, raw_text, story_dir)
        scene_list = self._extract_scenes(config, full_text, story_dir)
        scene_summaries, scene_metadatas = self._generate_summaries_and_metadata(config, scene_list)

        self._save_json(story_dir / "scene_summaries.json", scene_summaries)
        self._save_json(story_dir / "scene_metadatas.json", scene_metadatas)

        # self._generate_modalities(config, scene_summaries, scene_metadatas)
        # self._compose_video(config, scene_summaries, scene_metadatas)

        print("Text-to-Scene pipeline completed.")

    # 폴더 가져오기
    def _get_story_dir(self, config) -> Path:
        story_dir = Path(config.get("story_dir") or config.get("video_compose", {}).get("params", {}).get("story_dir", "generated_stories/example"))
        story_dir.mkdir(parents=True, exist_ok=True)
        return story_dir

    # 원본 텍스트 가져오기
    def _get_raw_text(self, config) -> str:
        raw_text = config.get("story_writer", {}).get("params", {}).get("full_context", "").strip()
        if not raw_text:
            raise ValueError("[ERROR] 'full_context'가 비어 있습니다. Whisper 또는 텍스트 로딩을 확인하세요.")
        return raw_text

    # 작성하기
    def _write_file(self, path: Path, content: str):
        path.write_text(content, encoding="utf-8")

    # 텍스트 정제하기
    def _refine_text(self, config, raw_text: str, story_dir: Path) -> str:
        print("[STEP 1] 전체 텍스트 정제 중...")
        refine_writer = init_tool_instance(config["refine_writer"])
        refined_text = refine_writer.call({"raw_text": raw_text})
        self._write_file(story_dir / "refined_text.txt", refined_text)

        print("[STEP 2] 고유명사 오류 수정(PostCorrectionAgent)...")
        post_corrector = init_tool_instance(config["post_correction"])
        corrected_text = post_corrector.call({"text": refined_text})
        self._write_file(story_dir / "full_text.txt", corrected_text)

        print("[DEBUG] 최종 텍스트 일부:\n", corrected_text[:300])
        return corrected_text

    # 신 추출하기
    def _extract_scenes(self, config, full_text: str, story_dir: Path) -> list:
        print("[STEP] 장면 추출 중...")
        scene_extractor = init_tool_instance(config["scene_extractor"])
        scene_list = scene_extractor.call({"full_text": full_text})
        self._save_json(story_dir / "scene_text.json", scene_list)
        return scene_list

    # summary와 meta 데이터 생성하기
    def _generate_summaries_and_metadata(self, config, scene_list: list):
        print("Scene별 대본, 메타, 등장인물 생성 중...")
        summary_writer = init_tool_instance(config["summary_writer"])
        meta_writer = init_tool_instance(config["meta_writer"])

        scene_summaries = []
        scene_metadatas = []

        for idx, scene in enumerate(tqdm(scene_list, desc="Generating summary/metadata per scene")):
            scene_id = scene.get("id", str(idx + 1))

            summary = self._safe_tool_call(summary_writer, scene, "summary", scene_id)
            metadata = self._safe_tool_call(meta_writer, scene, "metadata", scene_id)

            scene_summaries.append(summary)
            scene_metadatas.append(metadata)

        return scene_summaries, scene_metadatas

    def _safe_tool_call(self, tool, scene, mode: str, scene_id: str) -> dict:
        try:
            result = tool.call({"scene_text": [scene]})[0]
        except Exception as e:
            result = {
                "id": scene_id,
                "summary": f"[Error generating {mode}]: {e}"
            }
        return result
    
    # 결과 파일 저장하기 
    def _save_json(self, path: Path, data: list):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    # 모달리티 생성 및 비디오 합성 및 호출 가능
    def _generate_modalities(self, config, scene_summaries: list, scene_metadatas: list):
        print("Generating modality assets...")
        # 요약 결과를 각 페이지에 활용
        self.generate_modality_assets(config, scene_summaries, scene_metadatas)

    def _compose_video(self, config, scene_summaries: list, scene_metadatas: list):
        print("Composing storytelling video...")
        self.compose_storytelling_video(
            config,
            scene_summaries=scene_summaries,
            scene_metadatas=scene_metadatas,
            use_metadata_for_video=False  # ← 필요시 True로 설정 가능
        )

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
