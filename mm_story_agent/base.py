# 에이전트 등록 및 초기화 담당
# ABC 클래스는 향후 확장성을 위한 추상 클래스 기반 구조를 지원하기 위해 임포트됨
from abc import ABC

# 에이전트 이름(key)과 해당 클래스 이름(value)을 매핑하는 딕셔너리
# init_tool_instanace()가 해당 에이전트를 찾을 수 있도록
register_map = {
    'qwen': 'QwenAgent',
    'exaone': 'ExaoneAgent',
    'qa_outline_story_writer': 'QAOutlineStoryWriter',
    'musicgen_t2m': 'MusicGenAgent',
    'story_diffusion_t2i': 'StoryDiffusionAgent',
    'cosyvoice_tts': 'CosyVoiceAgent',
    'audioldm2_t2a': 'AudioLDM2Agent',
    'slideshow_video_compose': 'SlideshowVideoComposeAgent',
    'freesound_sfx_retrieval': 'FreesoundSfxAgent',
    'freesound_music_retrieval': 'FreesoundMusicAgent',
    'refine_writer': 'RefineWriterAgent',
    'scene_splitter': 'SceneExtractorAgent',
    'summary_writer': 'SummaryWriterAgent',
    'meta_writer': 'MetaWriterAgent',
}    

# 주어진 키에 따라 해당 에이전트 클래스를 현재 디렉토리로부터 동적으로 import
def import_from_register(key):
    value = register_map[key]  # 클래스 이름 추출
    exec(f'from . import {value}')  # exec로 동적 import 실행

# 도구 레지스트리를 위한 사용자 정의 클래스 (dict를 상속)
class ToolRegistry(dict):

    # 키가 처음 접근될 때 자동으로 모듈을 import
    def _import_key(self, key):
        try:
            import_from_register(key)  # 실패해도 전체 시스템이 죽지 않도록 예외 처리
        except Exception as e:
            print(f'import {key} failed, details: {e}')

    # 레지스트리에서 항목을 가져올 때 호출됨
    def __getitem__(self, key):
        if key not in self.keys():  # 키가 없으면 import 시도
            self._import_key(key)
        return super().__getitem__(key)

    # 키가 존재하는지 확인할 때 호출됨
    def __contains__(self, key):
        self._import_key(key)  # 존재 여부와 관계없이 먼저 import 시도
        return super().__contains__(key)

# 전역 레지스트리 객체 (모든 도구가 여기에 등록됨)
TOOL_REGISTRY = ToolRegistry()

# 에이전트 클래스를 등록하기 위한 데코레이터
def register_tool(name):
    def decorator(cls):
        TOOL_REGISTRY[name] = cls  # 클래스 등록
        return cls  # 원래 클래스 반환 (데코레이터 구조 유지)
    return decorator

# config 딕셔너리를 기반으로 에이전트 인스턴스를 초기화
# 예: {"tool": "qwen", "cfg": {...}} → QwenAgent({...})
def init_tool_instance(cfg):
    return TOOL_REGISTRY[cfg["tool"]](cfg["cfg"])
