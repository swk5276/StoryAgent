### Whisper 한국어 파인 튜닝 모델 사용 시 ### 

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


### Whisper 한국어 파인 튜닝 모델 사용 시 ### 

# "byoussef/whisper-large-v2-Ko"
# "seongsubae/openai-whisper-large-v3-turbo-ko-TEST"

from transformers import pipeline
import torch

def transcribe_audio(audio_path: str, model_name: str = "seongsubae/openai-whisper-large-v3-turbo-ko-TEST") -> str:
    try:
        print(f"[INFO] HuggingFace Whisper 모델 로드 중... (모델: {model_name})")

        pipe = pipeline(
            task="automatic-speech-recognition",
            model=model_name,
            device=0 if torch.cuda.is_available() else -1,
            return_timestamps=True  # 추가된 부분
        )

        result = pipe(audio_path)
        text = result["text"].strip()
        print(f"[INFO] 추출된 텍스트: {text[:50]}...")
        return text

    except Exception as e:
        print(f"[ERROR] Whisper 오류 발생: {e}")
        return ""

### Wav2Vec2Processor 모델 사용 시 ### 

# from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
# import torch
# import torchaudio

# def transcribe_audio(audio_path: str, model_name: str = "kresnik/wav2vec2-large-xlsr-korean") -> str:
#     try:
#         print(f"[INFO] HuggingFace Wav2Vec2 모델 로드 중... (모델: {model_name})")

#         # 모델과 토크나이저 불러오기
#         processor = Wav2Vec2Processor.from_pretrained(model_name)
#         model = Wav2Vec2ForCTC.from_pretrained(model_name)
#         model.eval()
#         device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
#         model.to(device)

#         # 오디오 로딩
#         speech_array, sampling_rate = torchaudio.load(audio_path)

#         # wav2vec2는 16kHz만 지원하므로 리샘플링 필요 시 적용
#         if sampling_rate != 16000:
#             resampler = torchaudio.transforms.Resample(orig_freq=sampling_rate, new_freq=16000)
#             speech_array = resampler(speech_array)
        
#         # 배치 형태로 변환
#         input_values = processor(speech_array.squeeze().numpy(), return_tensors="pt", sampling_rate=16000).input_values
#         input_values = input_values.to(device)

#         # 추론
#         with torch.no_grad():
#             logits = model(input_values).logits

#         predicted_ids = torch.argmax(logits, dim=-1)
#         transcription = processor.batch_decode(predicted_ids)[0].strip()

#         print(f"[INFO] 추출된 텍스트: {transcription[:50]}...")
#         return transcription

#     except Exception as e:
#         print(f"[ERROR] wav2vec2 오류 발생: {e}")
#         return ""
