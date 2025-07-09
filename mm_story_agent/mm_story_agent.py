# 시간 관련 기능을 위한 모듈
import time
# JSON 파일 저장 및 로드를 위한 모듈
import json
# 경로 처리를 위한 pathlib 모듈
from pathlib import Path
# 시스템 관련 기능을 위한 모듈
import sys
# PyTorch의 멀티프로세싱 기능을 사용하기 위한 모듈
import torch.multiprocessing as mp
# 멀티프로세싱 방식 설정 (spawn 방식으로 강제 설정)
mp.set_start_method("spawn", force=True)
from tqdm import tqdm
from tqdm import trange

# 사용자 정의 도구 인스턴스를 초기화하는 함수 불러오기
from .base import init_tool_instance

#전체 이야기 생성 파이프 라인의 중심 클래스 MMStoryAgent를 정의하고 실행하는 것

from mm_story_agent.prompts_en2 import (
    scene_expert_system,
    scene_amateur_questioner_system,
    scene_refined_output_system,
)


################# 멀티모달 스토리 에이전트를 정의하는 클래스
class MMStoryAgent:

    # 클래스 생성자
    def __init__(self) -> None:
        # 사용할 모달리티 목록 지정 ("speech", "music")
        self.modalities = ["speech", "music"]

    
    from tqdm import tqdm

    def run_text_scene_pipeline(self, config):
        from pathlib import Path
        import json

        story_dir = Path(config["story_dir"])
        story_dir.mkdir(parents=True, exist_ok=True)

        full_context = config["story_writer"]["params"]["full_context"]

        # 1. 텍스트 정제
        refine_writer = init_tool_instance(config["refine_writer"])
        full_text = refine_writer.call({"raw_text": full_context})
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

        # 4. 저장
        with open(story_dir / "scene_summaries.json", "w", encoding="utf-8") as f:
            json.dump(scene_summaries, f, indent=4, ensure_ascii=False)

        with open(story_dir / "scene_metadatas.json", "w", encoding="utf-8") as f:
            json.dump(scene_metadatas, f, indent=4, ensure_ascii=False)

        print("✅ Text-to-Scene pipeline completed.")




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
        # 1단계: 스토리 생성
        pages = self.write_story(config)

        # 생성된 페이지를 출력
        print("페이지 확인:")
        for i, page in enumerate(pages):
            print(f"--- Page {i+1} ---")
            print(page)
            print()
        
        # 여기서 강제 종료 → 아래 단계 실행되지 않음
        sys.exit()  # 이 줄이 핵심입니다

        # 모달리티 자산 생성 및 비디오 합성은 실행되지 않음 (현재는 주석처럼 무시됨)
        # images = self.generate_modality_assets(config, pages)
        self.compose_storytelling_video(config, pages)

from mm_story_agent.base import register_tool
from mm_story_agent.modality_agents.llm import QwenAgent  # QwenAgent 불러오기

# 텍스트 정제 및 교정하는 역할 
# 입력 : raw_text 출력 : full_text
@register_tool("RefineWriterAgent")
class RefineWriterAgent:
    def __init__(self, cfg):
        self.llm = QwenAgent(cfg)

    def call(self, params):
        print("[RefineWriterAgent] 전체 텍스트 정제 중")  # 진행 확인용 메시지
        prompt = params["raw_text"]
        response, _ = self.llm.call(prompt)
        print("[RefineWriterAgent] 전체 텍스트 정제 완료.")  # 완료 확인 메시지
        return response

    
import ast
# 전체 이야기를 장면 단위로 나눔
# 입력 : full_text / 처리 : LLM으로 장면을 추출
# 리스트 형식인지 확인하는 함수
def parse_list(output: str):
    try:
        parsed = ast.literal_eval(output)
        return isinstance(parsed, list)
    except Exception:
        return False

from tqdm import trange
import time  # optional: sleep() 넣고 싶다면 사용

@register_tool("SceneExtractorAgent")
class SceneExtractorAgent:
    def __init__(self, cfg):
        self.cfg = cfg
        self.temperature = cfg.get("temperature", 0.7)
        self.max_conv_turns = cfg.get("max_conv_turns", 3)
        self.llm_type = cfg.get("llm", "qwen")

        # 각 역할의 LLM 초기화
        print("[INFO] 전문가 LLM 초기화")
        self.expert = init_tool_instance({
            "tool": self.llm_type,
            "cfg": {
                "system_prompt": scene_expert_system,
                "track_history": False
            }
        })

        print("[INFO] 아마추어 LLM 초기화")
        self.amateur = init_tool_instance({
            "tool": self.llm_type,
            "cfg": {
                "system_prompt": scene_amateur_questioner_system,
                "track_history": False
            }
        })

        print("[INFO] 정제 LLM 초기화")
        self.refiner = init_tool_instance({
            "tool": self.llm_type,
            "cfg": {
                "system_prompt": scene_refined_output_system,
                "track_history": False
            }
        })

    def call(self, params):
        full_text = params["full_text"]
        dialogue = []

        print("\n[STEP 1] Generating initial scene draft (Expert)...")
        initial_scene, _ = self.expert.call(full_text, temperature=self.temperature)
        print(">>> Initial Scene Draft:\n", initial_scene.strip(), "\n")
        dialogue.append(f"Expert: {initial_scene.strip()}")

        print("[STEP 2] Starting Q&A Refinement Loop...\n")
        for turn in trange(self.max_conv_turns, desc="Q&A Turns"):
            print(f"\n--- Turn {turn+1} ---")
            history = "\n".join(dialogue)

            question, _ = self.amateur.call(f"{full_text}\n{history}", temperature=self.temperature)
            print(f"[Amateur's Question]: {question.strip()}")
            dialogue.append(f"Amateur: {question.strip()}")

            answer, _ = self.expert.call(f"{full_text}\nQuestion: {question.strip()}", temperature=self.temperature)
            print(f"[Expert's Answer]: {answer.strip()}")
            dialogue.append(f"Expert: {answer.strip()}")

        print("\n[STEP 3] Refining final scene list...")
        final_prompt = "\n".join(dialogue)
        final_scene_list, success = self.refiner.call(
            f"{full_text}\n{final_prompt}",
            success_check_fn=parse_list,
            temperature=self.temperature
        )

        if not success:
            print("[ERROR] Scene extraction failed.")
            raise ValueError("Scene extraction failed.")

        print("\n✅ Scene extraction complete. Final scene list:")
        print(final_scene_list)
        return eval(final_scene_list)



@register_tool("SummaryWriterAgent")
class SummaryWriterAgent:
    def __init__(self, cfg):
        self.llm = QwenAgent(cfg)
    def call(self, params):
        joined = "\n".join(params["scene_text"])
        response, _ = self.llm.call(f"Summarize the story: {joined}")
        return response

@register_tool("MetaWriterAgent")
class MetaWriterAgent:
    def __init__(self, cfg):
        self.llm = QwenAgent(cfg)
    def call(self, params):
        joined = "\n".join(params["scene_text"])
        response, _ = self.llm.call(f"Extract metadata (genre, tone, setting, themes, target age) from:\n{joined}")
        return response  # json 파싱 원할 경우 추후 추가
