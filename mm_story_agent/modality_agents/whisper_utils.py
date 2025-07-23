from transformers import pipeline
import torch
# from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
# import whisper
import torch
import torchaudio
import os
WHISPER_MODELS = [
    "seongsubae/openai-whisper-large-v3-turbo-ko-TEST",
    "openai/whisper-large-v3",
    "openai/whisper-medium"
]

# 음성 인식 텍스트 삽입하기
def inject_whisper_text_to_config(config, whisper_text: str):
    # full_context field
    if "story_writer" not in config:
        config["story_writer"] = {}
    if "params" not in config["story_writer"]:
        config["story_writer"]["params"] = {}
    config["story_writer"]["params"]["full_context"] = whisper_text
    print("[INFO] Whisper 텍스트가 story_writer.params.full_context에 삽입되었습니다.")


def transcribe_audio(audio_path: str, model_name: str) -> str:
    print(f"[INFO] HuggingFace Whisper 모델 로드 중... (모델: {model_name})")
    pipe = pipeline(
        task="automatic-speech-recognition",
        model=model_name,
        device=0 if torch.cuda.is_available() else -1,
        return_timestamps=True
    )
    result = pipe(audio_path)
    return result["text"].strip()

def transcribe_and_save_all_models(audio_path: str, story_dir: str) -> list:
    all_texts = []
    for i, model_name in enumerate(WHISPER_MODELS, start=1):
        text = transcribe_audio(audio_path, model_name)
        all_texts.append(text)
        file_path = os.path.join(story_dir, f"full_text_raw{i}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[INFO] {file_path} 저장 완료")
    return all_texts


def summarize_and_save_final_text(all_texts: list, story_dir: str, llm_agent) -> str:
    prompt = f"""
다음은 서로 다른 Whisper 모델에서 추출된 세 가지 음성 인식 결과입니다. 이 중 가장 정확하고 자연스러운 표현을 선택하여 최종 텍스트로 통합해 주세요. 의미가 충돌하면 신뢰할 수 있는 표현을 유지하고 오류는 고쳐 주세요.

### 결과 1:
{all_texts[0]}

### 결과 2:
{all_texts[1]}

### 결과 3:
{all_texts[2]}

최종 통합된 전체 텍스트만 출력해 주세요. 해설은 제외합니다.
"""
    final_text, _ = llm_agent.call(prompt)
    final_path = os.path.join(story_dir, "full_text_raw.txt")
    with open(final_path, "w", encoding="utf-8") as f:
        f.write(final_text.strip())
    print(f"[INFO] 최종 통합 텍스트가 {final_path}에 저장되었습니다.")
    return final_text.strip()

# def inject_whisper_text_to_config(config, whisper_text: str):
#     if "story_writer" not in config:
#         config["story_writer"] = {}
#     if "params" not in config["story_writer"]:
#         config["story_writer"]["params"] = {}
#     config["story_writer"]["params"]["full_context"] = whisper_text
#     print("[INFO] Whisper 텍스트가 story_writer.params.full_context에 삽입되었습니다.")

# FineTuning된 whisper 모델 사용 시
# def transcribe_audio(audio_path: str, model_name: str = "seongsubae/openai-whisper-large-v3-turbo-ko-TEST") -> str:
#     try:
#         print(f"[INFO] HuggingFace Whisper 모델 로드 중... (모델: {model_name})")

#         pipe = pipeline(
#             task="automatic-speech-recognition",
#             model=model_name,
#             device=0 if torch.cuda.is_available() else -1,
#             return_timestamps=True  # 추가된 부분
#         )

#         result = pipe(audio_path)
#         text = result["text"].strip()
#         print(f"[INFO] 추출된 텍스트: {text[:50]}...")
#         return text

#     except Exception as e:
#         print(f"[ERROR] Whisper 오류 발생: {e}")
#         return ""

# Base Whisper 모델 사용 시
def transcribe_audio2(audio_path: str, model_size: str = "large-v3", lang: str = "ko") -> str:
    try:
        print(f"[INFO] Whisper 모델 로드 중... (모델: {model_size})")
        model = whisper.load_model(model_size)
        result = model.transcribe(audio_path, language=lang, task="transcribe")
        print("[DEBUG] Whisper 감지 언어:", result.get("language", "unknown"))
        return result["text"].strip()
    except Exception as e:
        print(f"[ERROR] Whisper 오류 발생: {e}")
        return ""

# Wav2Vec2Processor 모델 사용 시 
def transcribe_audio3(audio_path: str, model_name: str = "kresnik/wav2vec2-large-xlsr-korean") -> str:
    try:
        print(f"[INFO] HuggingFace Wav2Vec2 모델 로드 중... (모델: {model_name})")

        # 모델과 토크나이저 불러오기
        processor = Wav2Vec2Processor.from_pretrained(model_name)
        model = Wav2Vec2ForCTC.from_pretrained(model_name)
        model.eval()
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)

        # 오디오 로딩
        speech_array, sampling_rate = torchaudio.load(audio_path)

        # wav2vec2는 16kHz만 지원하므로 리샘플링 필요 시 적용
        if sampling_rate != 16000:
            resampler = torchaudio.transforms.Resample(orig_freq=sampling_rate, new_freq=16000)
            speech_array = resampler(speech_array)
        
        # 배치 형태로 변환
        input_values = processor(speech_array.squeeze().numpy(), return_tensors="pt", sampling_rate=16000).input_values
        input_values = input_values.to(device)

        # 추론
        with torch.no_grad():
            logits = model(input_values).logits

        predicted_ids = torch.argmax(logits, dim=-1)
        transcription = processor.batch_decode(predicted_ids)[0].strip()

        print(f"[INFO] 추출된 텍스트: {transcription[:50]}...")
        return transcription

    except Exception as e:
        print(f"[ERROR] wav2vec2 오류 발생: {e}")
        return ""

