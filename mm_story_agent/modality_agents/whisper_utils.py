# mm_story_agent/utils/whisper_utils.py

import whisper

def transcribe_audio(audio_path: str, model_size: str = "base", lang: str = "ko") -> str:
    """
    Whisper로 음성 파일을 텍스트로 변환하여 반환합니다.
    """
    try:
        print(f"[INFO] Whisper 모델 로드 중... (모델: {model_size})")
        model = whisper.load_model(model_size)
        result = model.transcribe(audio_path, language=lang)
        print("[DEBUG] Whisper 감지 언어:", result.get("language", "unknown"))
        return result["text"].strip()
    except Exception as e:
        print(f"[ERROR] Whisper 오류 발생: {e}")
        return ""
