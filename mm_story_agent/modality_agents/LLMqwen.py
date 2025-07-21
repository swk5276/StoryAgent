# 타입 힌트와 콜백 함수 정의를 위한 타입 모듈
from typing import Dict, Callable
import os

# (예비용) DashScope API 모듈 (현재는 사용되지 않음)
from dashscope import Generation

# 툴 등록을 위한 데코레이터
from mm_story_agent.base import register_tool

# OpenAI 호환 클라이언트 (Together.ai, Dashscope 등 사용 가능)
from openai import OpenAI

# "qwen"이라는 이름으로 에이전트를 등록
@register_tool("qwen")
class QwenAgent(object):
    # 초기화 함수
    def __init__(self, config: Dict):
        # system_prompt 설정이 있는 경우 시스템 메시지를 히스토리에 추가
        self.system_prompt = config.get("system_prompt")
        track_history = config.get("track_history", False)

        if self.system_prompt is None:
            self.history = []  # 시스템 프롬프트가 없으면 빈 히스토리
        else:
            self.history = [
                {"role": "system", "content": self.system_prompt}
            ]
        self.track_history = track_history  # 대화 히스토리 유지 여부

    # 응답이 유효한지 간단하게 확인하는 함수
    def basic_success_check(self, response):
        if not response or response.strip() == "":
            print(f"Invalid response: {response}")
            return False
        return True  # 정상 응답이면 True

    # 실제 LLM 호출 함수
    # 사용 모델 : qwen2-72b-instruct  /  lgai/exaone-3-5-32b-instruct  /  
    def call(self,
             prompt: str,  # LLM에 입력으로 줄 프롬프트 문자열
             model_name: str = "qwen2-72b-instruct",  # 사용할 모델 이름
             # model_name 예시: "lgai/exaone-3-5-32b-instruct", "gpt-4o"
             top_p: float = 0.95,  # 확률 누적 기반 샘플링 (다양성 조절)
             temperature: float = 1.0,  # 랜덤성 조절 (창의성 정도)
             seed: int = 1,  # 동일한 결과를 얻기 위한 시드 값
             max_length: int = 1024,  # 최대 출력 길이 (토큰 수)
             max_try: int = 5,  # 실패했을 때 최대 재시도 횟수
             success_check_fn: Callable = None  # 결과 유효성 체크 함수
             ):
        # 현재 사용 중인 모델명을 로그로 출력
        print(f"[INFO] Using model: {model_name}")

        # 사용자 입력을 히스토리에 추가
        self.history.append({
            "role": "user",
            "content": prompt
        })

        success = False
        response = None
        try_times = 0

        # OpenAI 호환 클라이언트 생성 (현재는 Dashscope 방식 사용)
        client = OpenAI(
            # 알리바바 DashScope API 키 및 엔드포인트
            api_key="sk-c6abdec50898482e89a9d5c94741efe1",
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
            
            # 아래는 주석 처리된 Together.ai용 설정
            # api_key="adb805e28e2ac4326e301c3d24ee8870e427e81006645089c49fdf23ab52216b",
            # base_url="https://api.together.xyz/v1"
        )

        # 최대 max_try 횟수만큼 재시도 루프
        while try_times < max_try:
            # LLM에 메시지 히스토리를 보내고 응답 생성
            completion = client.chat.completions.create(
                model=model_name,
                messages=self.history,
                top_p=top_p,
                temperature=temperature,
                seed=seed,
                max_tokens=max_length
            )

            # 응답 텍스트 추출
            response_text = completion.choices[0].message.content

            # 성공 판별 함수가 없는 경우 항상 성공으로 간주
            if success_check_fn is None:
                success_check_fn = lambda x: True

            # 응답이 유효하다면 종료
            if self.basic_success_check(response_text) and success_check_fn(response_text):
                response = response_text
                # assistant 역할로 응답을 히스토리에 추가
                self.history.append({
                    "role": "assistant",
                    "content": response
                })
                success = True
                break  # 성공했으므로 반복 종료
            else:
                try_times += 1  # 실패했으므로 재시도 횟수 증가

        # track_history가 False일 경우 히스토리 초기화
        if not self.track_history:
            if self.system_prompt is not None:
                self.history = self.history[:1]  # 시스템 프롬프트만 남김
            else:
                self.history = []  # 전체 초기화

        # 최종 응답 및 성공 여부 반환
        return response, success

