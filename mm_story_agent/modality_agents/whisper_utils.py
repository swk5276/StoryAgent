# # mm_story_agent/utils/whisper_utils.py

# import whisper

# def transcribe_audio(audio_path: str, model_size: str = "large-v3", lang: str = "ko") -> str:
#     try:
#         print(f"[INFO] Whisper 모델 로드 중... (모델: {model_size})")
#         model = whisper.load_model(model_size)
#         result = model.transcribe(audio_path, language=lang, task="transcribe")
#         print("[DEBUG] Whisper 감지 언어:", result.get("language", "unknown"))
#         return result["text"].strip()
#     except Exception as e:
#         print(f"[ERROR] Whisper 오류 발생: {e}")
#         return ""


# mm_story_agent/utils/whisper_utils.py

# "byoussef/whisper-large-v2-Ko"
# "seongsubae/openai-whisper-large-v3-turbo-ko-TEST"
from transformers import pipeline
import torch

def transcribe_audio(audio_path: str, model_name: str = "byoussef/whisper-large-v2-Ko") -> str:
    try:
        print(f"[INFO] HuggingFace Whisper 모델 로드 중... (모델: {model_name})")

        pipe = pipeline(
            task="automatic-speech-recognition",
            model=model_name,
            device=0 if torch.cuda.is_available() else -1,
            return_timestamps=True  # ✅ 추가된 부분
        )

        result = pipe(audio_path)
        text = result["text"].strip()
        print(f"[INFO] 추출된 텍스트: {text[:50]}...")
        return text

    except Exception as e:
        print(f"[ERROR] Whisper 오류 발생: {e}")
        return ""

