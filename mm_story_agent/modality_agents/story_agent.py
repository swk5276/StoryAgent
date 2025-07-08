# JSON 데이터 처리용 모듈
import json
# 타입 힌트를 위한 모듈
from typing import Dict
# 무작위 수 생성을 위한 모듈
import random
# tqdm: 반복문의 진행 상황을 보여주는 라이브러리
from tqdm import trange, tqdm

# LLM 출력 결과를 확인하는 함수
from ..utils.llm_output_check import parse_list
# 도구 등록 및 초기화 함수
from ..base import register_tool, init_tool_instance
# 시스템 프롬프트들 불러오기
from ..prompts_en2 import question_asker_system, expert_system, \
    dlg_based_writer_system, dlg_based_writer_prompt, chapter_writer_system

# JSON 형태의 outline이 유효한지 검사하는 함수
def json_parse_outline(outline):
    # 코드 블록 마크다운(```json 등)을 제거
    outline = outline.strip("```json").strip("```")
    try:
        # 문자열을 JSON으로 파싱
        outline = json.loads(outline)
        # 딕셔너리인지 확인
        if not isinstance(outline, dict):
            return False
        # 필요한 키만 포함되어 있는지 확인
        if outline.keys() != {"story_title", "story_outline"}:
            return False
        # 각 챕터가 필요한 키를 가지고 있는지 확인
        for chapter in outline["story_outline"]:
            if chapter.keys() != {"chapter_title", "chapter_summary"}:
                return False
    except json.decoder.JSONDecodeError:
        # JSON 파싱 실패
        return False
    return True  # 모든 조건 통과 시 True 반환

# 질문 생성 LLM 과 전문가 역할 LLM을 통해 Q & A 대화 생성 
@register_tool("qa_outline_story_writer")
class QAOutlineStoryWriter:

    # 클래스 생성자
    def __init__(self, cfg: Dict):
        self.cfg = cfg
        # LLM 생성 온도 설정 (기본값 1.0)
        self.temperature = cfg.get("temperature", 1.0)
        # 대화 최대 턴 수 설정
        self.max_conv_turns = cfg.get("max_conv_turns", 3)
        # 생성할 아웃라인 개수 설정
        self.num_outline = cfg.get("num_outline", 4)
        # 사용할 LLM 종류 설정
        self.llm_type = cfg.get("llm", "qwen")

    # 대화 기반 아웃라인을 JSON 형태로 생성하는 함수
    def generate_outline(self, params):
        # params: 이야기 설정 정보 (예: 제목, 주인공 등)

        # 질문 생성용 LLM 초기화
        asker = init_tool_instance({
            "tool": self.llm_type,
            "cfg": {
                "system_prompt": question_asker_system,
                "track_history": False
            }
        })

        # 전문가 역할 LLM 초기화
        expert = init_tool_instance({
            "tool": self.llm_type,
            "cfg": {
                "system_prompt": expert_system,
                "track_history": False
            }
        })

        # 질문-답변 기록 저장 리스트
        dialogue = []
        for turn in trange(self.max_conv_turns):  # 최대 지정된 횟수만큼 반복
            dialogue_history = "\n".join(dialogue)  # 현재까지 대화 히스토리 결합

            # 변경
            full_context = params.get("full_context", str(params))
            # 질문 생성
            question, success = asker.call(
                f"Story setting: {full_context}\nDialogue history: \n{dialogue_history}\n",
                temperature=self.temperature
            )
            question = question.strip()

            # '대화 종료' 문구가 나오면 종료
            if question == "Thank you for your help!":
                break

            # 질문을 대화 기록에 추가
            dialogue.append(f"You: {question}")

            # 전문가의 답변 생성
            answer, success = expert.call(
                f"Story setting: {full_context}\nQuestion: \n{question}\nAnswer: ",
                temperature=self.temperature
            )
            answer = answer.strip()
            dialogue.append(f"Expert: {answer}")

        # 아웃라인 작성기 LLM 초기화
        writer = init_tool_instance({
            "tool": self.llm_type,
            "cfg": {
                "system_prompt": dlg_based_writer_system,
                "track_history": False
            }
        })
        # full_context 가져오기
        full_context = params.get("full_context", "")
        # 아웃라인 작성용 프롬프트 생성
        writer_prompt = dlg_based_writer_prompt.format(
            story_setting=full_context,
            dialogue_history="\n".join(dialogue),
            num_outline=self.num_outline
        )

        # 아웃라인 생성 시도
        outline, success = writer.call(writer_prompt, success_check_fn=json_parse_outline)

        # 디버깅용 출력
        try:
            preview_outline = outline.replace("```json", "").replace("```", "").strip()
            parsed_outline = json.loads(preview_outline)
            print("🔍 [DEBUG] Parsed Outline:")
            print(json.dumps(parsed_outline, ensure_ascii=False, indent=4))
        except Exception as e:
            print("❌ JSON 파싱 실패. 원본 출력:")
            print(repr(outline))
        # 유효하지 않은 결과인 경우 에러 발생
        if not outline or not outline.strip():
            raise ValueError(f"LLM에서 유효한 outline을 받지 못했습니다: {repr(outline)}")

        # 마크다운 JSON 블록 제거
        outline = outline.replace("```json", "").replace("```", "").strip()

        # JSON 파싱
        outline = json.loads(outline)

        # 최종 outline 반환
        return outline

    # 아웃라인을 기반으로 챕터별 상세 이야기 생성
    def generate_story_from_outline(self, outline):
        # 챕터 작성용 LLM 초기화
        chapter_writer = init_tool_instance({
            "tool": self.llm_type,
            "cfg": {
                "system_prompt": chapter_writer_system,
                "track_history": False
            }
        })

        all_pages = []  # 전체 이야기 페이지 리스트
        for idx, chapter in enumerate(tqdm(outline["story_outline"])):
            # 현재까지의 내용과 새로운 챕터 정보를 입력으로 전달
            chapter_detail, success = chapter_writer.call(
                json.dumps(
                    {
                        "completed_story": all_pages,
                        "current_chapter": chapter
                    },
                    ensure_ascii=False
                ),
                success_check_fn=parse_list,  # 출력이 리스트 형태인지 확인
                temperature=self.temperature
            )

            # 실패한 경우 시드 랜덤값 주어 재시도
            while success is False:
                chapter_detail, success = chapter_writer.call(
                    json.dumps(
                        {
                            "completed_story": all_pages,
                            "current_chapter": chapter
                        },
                        ensure_ascii=False
                    ),
                    seed=random.randint(0, 100000),  # 시드 변경
                    temperature=self.temperature,
                    success_check_fn=parse_list
                )

            # 문자열로 된 리스트를 파싱 (eval 사용)
            pages = [page.strip() for page in eval(chapter_detail)]
            all_pages.extend(pages)  # 전체 페이지에 추가

        # 모든 페이지 반환
        return all_pages

    # 전체 파이프라인 실행 함수
    def call(self, params):
        # 1단계: 아웃라인 생성
        outline = self.generate_outline(params)
        # 2단계: 아웃라인 기반 챕터별 이야기 생성
        pages = self.generate_story_from_outline(outline)
        # 최종 페이지 리스트 반환
        return pages
