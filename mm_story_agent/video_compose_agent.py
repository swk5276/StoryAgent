from pathlib import Path
from typing import List, Union
import random
import re
from datetime import timedelta

from tqdm import trange
import numpy as np
import librosa
import cv2
from zhon.hanzi import punctuation as zh_punc
from moviepy.editor import ImageClip, AudioFileClip, CompositeAudioClip, \
    CompositeVideoClip, ColorClip, VideoFileClip, VideoClip, TextClip, concatenate_audioclips 
import moviepy.video.compositing.transitions as transfx
from moviepy.audio.AudioClip import AudioArrayClip
from moviepy.audio.fx.all import audio_loop
from moviepy.video.tools.subtitles import SubtitlesClip

from mm_story_agent.base import register_tool


# 1. 기본 경로 설정
# 2. 각 페이지에 대해 반복 작업
# 음성 TTS 로드 : 페이지 하나마다 .wav 또는 여러조각의 p1_0.wav, p1_1.wav 등 병합 , 페이드인 , 페이드 아웃, 슬라이드 전용 무음 구간 추가
# 이미지 불러오기 : 이미지 파일을 읽어 speech_clip 길이에 맞게 설정 , 확대 또는 이동 효과 적용
# 효과음 삽입 : sound.wav 파일 존재 시 반복 볼륨 조절하여 speech_clip과 믹스 
# 슬라이드 효과로 클립 연결
# 자막 영역 추가 및 랜더링

# 음성을 텍스트로 변환 생성
from typing import List, Union
from pathlib import Path
from datetime import timedelta

def generate_srt(timestamps: List,
                 captions: List,
                 save_path: Union[str, Path],
                 max_single_length: int = 30):
    """
    자막의 시작/종료 시간과 텍스트를 기반으로 SRT 파일을 생성하는 함수

    Parameters:
    - timestamps (List[Tuple[float, float]]): 각 자막 구간의 (시작, 종료) 시간을 초 단위로 담은 리스트
    - captions (List[str]): 각 자막에 대응하는 문자열 리스트
    - save_path (str or Path): 생성된 .srt 파일을 저장할 경로
    - max_single_length (int): 한 자막 줄의 최대 문자 수 (기본값: 30)
    """

    # 초 단위 시간을 SRT 형식의 시:분:초,밀리초 문자열로 변환하는 내부 함수
    def format_time(seconds: float) -> str:
        td = timedelta(seconds=seconds)  # 초를 timedelta로 변환
        total_seconds = int(td.total_seconds())  # 총 정수 초
        millis = int((td.total_seconds() - total_seconds) * 1000)  # 밀리초 부분 계산
        hours, remainder = divmod(total_seconds, 3600)  # 시, 분:초 계산
        minutes, seconds = divmod(remainder, 60)        # 분, 초 계산
        return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"  # SRT 포맷 반환

    srt_content = []  # 전체 자막 문자열을 담을 리스트
    num_caps = len(timestamps)  # 자막 개수

    for idx in range(num_caps):
        start_time, end_time = timestamps[idx]  # 시작/종료 시간 추출
        # 긴 자막 문장을 max_single_length 길이에 따라 줄바꿈 처리 (함수 외부에 정의되어 있어야 함)
        caption_chunks = split_caption(captions[idx], max_single_length).split("\n")
        num_chunks = len(caption_chunks)

        if num_chunks == 0:
            continue  # 빈 자막은 건너뜀

        # 각 줄마다 배정될 자막 구간 시간 (자막 전체 시간 / 줄 수)
        segment_duration = (end_time - start_time) / num_chunks

        for chunk_idx, chunk in enumerate(caption_chunks):
            # 각 자막 줄의 시작/종료 시간 계산
            chunk_start_time = start_time + segment_duration * chunk_idx
            chunk_end_time = start_time + segment_duration * (chunk_idx + 1)

            # SRT 포맷 시간 문자열로 변환
            start_time_str = format_time(chunk_start_time)
            end_time_str = format_time(chunk_end_time)

            # SRT 형식에 맞는 텍스트 조립
            srt_content.append(
                f"{len(srt_content) // 2 + 1}\n"  # 자막 번호
                f"{start_time_str} --> {end_time_str}\n"  # 시간 구간
                f"{chunk}\n\n"  # 자막 텍스트 및 줄바꿈
            )

    # 완성된 SRT 내용을 파일로 저장
    with open(save_path, 'w') as srt_file:
        srt_file.writelines(srt_content)


# 자막을 추가
def add_caption(captions: List,  # 자막 텍스트 리스트
                srt_path: Union[str, Path],  # 생성할 SRT 파일 경로
                timestamps: List,  # 자막의 시작/종료 시간 리스트 (초 단위)
                video_clip: VideoClip,  # 자막을 입힐 원본 영상 클립
                max_single_length: int = 30,  # 자막 한 줄당 최대 글자 수
                **caption_config):  # TextClip에 들어갈 설정 (폰트, 색상 등)
    
    generate_srt(timestamps, captions, srt_path, max_single_length)  # SRT 자막 파일 생성

    generator = lambda txt: TextClip(txt, **caption_config)  # 자막 텍스트로 TextClip 생성하는 함수 정의
    subtitles = SubtitlesClip(srt_path.__str__(), generator)  # SRT 파일을 읽어 SubtitlesClip 생성
    captioned_clip = CompositeVideoClip([video_clip,  # 원본 영상에
                                         subtitles.set_position(("center", "bottom"), relative=True)])  # 자막을 하단 중앙에 위치시켜 합성

    return captioned_clip  # 자막이 입혀진 영상 클립 반환

def split_keep_separator(text, separator):  # 주어진 구분자를 기준으로 문자열을 나누되, 구분자도 결과에 포함시킴
    pattern = f'([{re.escape(separator)}])'  # separator를 이스케이프 처리하여 정규표현식 패턴 생성 (구분자를 그룹으로 캡처)
    pieces = re.split(pattern, text)  # 정규식 기준으로 split → 구분자도 결과 리스트에 포함됨
    return pieces  # 나눈 조각들 리스트 반환


def split_caption(caption, max_length=30):  # 자막 문장을 최대 글자 수에 따라 줄바꿈 처리
    lines = []  # 결과 줄들을 담을 리스트

    # 영어 여부 판별: caption의 첫 글자가 알파벳이면 영어로 판단
    if ord(caption[0]) >= ord("a") and ord(caption[0]) <= ord("z") or ord(caption[0]) >= ord("A") and ord(caption[0]) <= ord("Z"):
        words = caption.split(" ")  # 공백 기준으로 단어 나누기
        current_words = []  # 현재 줄에 들어갈 단어들

        for word in words:
            if len(" ".join(current_words + [word])) <= max_length:  # 현재 줄에 단어 추가해도 max_length 이하면
                current_words += [word]  # 단어 추가
            else:
                if current_words:  # 현재 줄이 비어있지 않으면
                    lines.append(" ".join(current_words))  # 줄 완성하여 추가
                    current_words = []  # 다음 줄 준비

        if current_words:  # 마지막 줄 처리
            lines.append(" ".join(current_words))

    else:
        # 영어가 아니면 (중국어 등) 문장 부호 기준으로 분리
        sentences = split_keep_separator(caption, zh_punc)  # zh_punc는 중국어 문장부호들(예: 。！？)
        current_line = ""

        for sentence in sentences:
            if len(current_line + sentence) <= max_length:  # 문장 추가해도 길이 제한 안 넘으면
                current_line += sentence  # 문장 이어붙이기
            else:
                if current_line:  # 현재 줄이 비어있지 않으면
                    lines.append(current_line)  # 줄 추가
                    current_line = ""  # 초기화

                if sentence.startswith(tuple(zh_punc)):  # 문장 부호로 시작하면 (예: "。새 문장")
                    if lines:
                        lines[-1] += sentence[0]  # 이전 줄 끝에 문장부호 붙이기
                    current_line = sentence[1:]  # 나머지 문장만 current_line에 추가
                else:
                    current_line = sentence  # 그냥 넣기

        if current_line:  # 마지막 줄 처리
            lines.append(current_line.strip())

    return '\n'.join(lines)  # 줄바꿈으로 연결된 자막 문자열 반환



def add_bottom_black_area(clip: VideoFileClip,  # 처리할 원본 영상 클립
                          black_area_height: int = 64):  # 추가할 검정 영역의 높이 (기본값: 64)
    """
    Add a black area at the bottom of the video clip (for captions).

    Args:
        clip (VideoFileClip): Video clip to be processed.
        black_area_height (int): Height of the black area.

    Returns:
        VideoFileClip: Processed video clip.
    """
    black_bar = ColorClip(size=(clip.w, black_area_height),  # 영상의 가로 너비와 지정 높이로 검정색 클립 생성
                          color=(0, 0, 0),  # RGB (0, 0, 0) = 검정색
                          duration=clip.duration)  # 원본 영상과 같은 재생 시간으로 설정

    extended_clip = CompositeVideoClip([clip,  # 원본 영상과
                                        black_bar.set_position(("center", "bottom"))])  # 검정 배경을 하단 중앙에 겹쳐 합성

    return extended_clip  # 하단에 검정 영역이 추가된 영상 클립 반환


def add_zoom_effect(clip, speed=1.0, mode='in', position='center'):  # 줌 효과를 추가하는 함수. 'in' 또는 'out' 방향 지정 가능
    fps = clip.fps  # 프레임 속도 (frames per second)
    duration = clip.duration  # 클립 길이 (초)
    total_frames = int(duration * fps)  # 총 프레임 수 계산

    def main(getframe, t):  # t초 시점의 프레임에 적용할 변환 함수
        frame = getframe(t)  # 해당 시간의 프레임 가져오기
        h, w = frame.shape[: 2]  # 프레임의 높이(h), 너비(w)
        i = t * fps  # 현재 프레임 인덱스 계산

        if mode == 'out':  # 줌 아웃일 경우 프레임 순서를 반대로 계산
            i = total_frames - i

        zoom = 1 + (i * ((0.1 * speed) / total_frames))  # 현재 줌 배율 계산 (시간에 따라 점점 커지거나 작아짐)

        # 위치에 따라 이동할 x, y 계산
        positions = {
            'center':  [(w - (w * zoom)) / 2,  (h - (h  *  zoom)) / 2],
            'left': [0, (h - (h * zoom)) / 2],
            'right': [(w - (w * zoom)), (h - (h * zoom)) / 2],
            'top': [(w - (w * zoom)) / 2, 0],
            'topleft': [0, 0],
            'topright': [(w - (w * zoom)), 0],
            'bottom': [(w - (w * zoom)) / 2, (h - (h * zoom))],
            'bottomleft': [0, (h - (h * zoom))],
            'bottomright': [(w - (w * zoom)), (h - (h * zoom))]
        }

        tx, ty = positions[position]  # 줌 위치의 변환 이동값 추출
        M = np.array([[zoom, 0, tx], [0, zoom, ty]])  # 줌 + 이동을 위한 2D 변환 행렬 구성
        frame = cv2.warpAffine(frame, M, (w, h))  # 프레임에 변환 적용 (크기 유지)
        return frame  # 처리된 프레임 반환

    return clip.fl(main)  # 프레임 처리 함수로 클립 변환


def add_move_effect(clip, direction="left", move_raito=0.95):  # 이동 효과 적용 함수. 방향(left/right)과 줌 비율 설정

    orig_width = clip.size[0]  # 원본 영상의 너비
    orig_height = clip.size[1]  # 원본 영상의 높이

    new_width = int(orig_width / move_raito)  # 이동을 위한 확대 영상의 너비 계산
    new_height = int(orig_height / move_raito)  # 확대된 영상의 높이 계산
    clip = clip.resize(width=new_width, height=new_height)  # 영상 확대 (이동 여백 확보)

    if direction == "left":  # 왼쪽으로 이동할 경우
        start_position = (0, 0)  # 처음 위치는 왼쪽
        end_position = (orig_width - new_width, 0)  # 끝 위치는 오른쪽으로 이동
    elif direction == "right":  # 오른쪽으로 이동할 경우
        start_position = (orig_width - new_width, 0)  # 처음 위치는 오른쪽 끝
        end_position = (0, 0)  # 끝 위치는 왼쪽

    duration = clip.duration  # 영상 길이(초)

    # 시간 t에 따라 위치를 선형 보간하여 이동 효과 적용
    moving_clip = clip.set_position(
        lambda t: (start_position[0] + (
            end_position[0] - start_position[0]) / duration * t, start_position[1])
    )

    # 원본 해상도에 맞춰 이동 영상 합성 (크롭 효과처럼 동작)
    final_clip = CompositeVideoClip([moving_clip], size=(orig_width, orig_height))

    return final_clip  # 이동 효과가 적용된 최종 영상 반환


def add_slide_effect(clips, slide_duration):  # 여러 클립에 슬라이드 전환 효과를 적용해 이어붙이는 함수
    ####### CAUTION: requires at least `slide_duration` of silence at the end of each clip #######
    durations = [clip.duration for clip in clips]  # 각 클립의 재생 시간 저장

    first_clip = CompositeVideoClip(
        [clips[0].fx(transfx.slide_out, duration=slide_duration, side="left")]  # 첫 번째 클립은 왼쪽으로 슬라이드 아웃
    ).set_start(0)  # 시작 시간 0초

    slide_out_sides = ["left"]  # 첫 번째 클립의 슬라이드 아웃 방향 저장
    videos = [first_clip]  # 결과 클립 리스트 초기화

    out_to_in_mapping = {"left": "right", "right": "left"}  # 슬라이드 아웃 방향 → 슬라이드 인 방향 매핑

    for idx, clip in enumerate(clips[1:-1], start=1):  # 중간 클립들을 순회
        # 이전 클립의 슬라이드 아웃 방향에 따라 현재 클립의 슬라이드 인 방향 결정
        slide_in_side = out_to_in_mapping[slide_out_sides[-1]]

        slide_out_side = "left" if random.random() <= 0.5 else "right"  # 현재 클립의 슬라이드 아웃 방향 랜덤 선택
        slide_out_sides.append(slide_out_side)  # 방향 저장

        videos.append(
            (
                CompositeVideoClip(
                    [clip.fx(transfx.slide_in, duration=slide_duration, side=slide_in_side)]  # 슬라이드 인 적용
                )
                .set_start(sum(durations[:idx]) - (slide_duration) * idx)  # 시작 시간 계산 (슬라이드 시간 고려)
                .fx(transfx.slide_out, duration=slide_duration, side=slide_out_side)  # 슬라이드 아웃 적용
            )
        )

    last_clip = CompositeVideoClip(
        [clips[-1].fx(transfx.slide_in, duration=slide_duration, side=out_to_in_mapping[slide_out_sides[-1]])]  # 마지막 클립은 이전 방향에 맞게 슬라이드 인만 적용
    ).set_start(sum(durations[:-1]) - slide_duration * (len(clips) - 1))  # 마지막 클립의 시작 시간 계산
    videos.append(last_clip)  # 마지막 클립 추가

    video = CompositeVideoClip(videos)  # 모든 클립을 합쳐 최종 영상 생성
    return video  # 최종 영상 반환


def compose_video(story_dir: Union[str, Path],  # 스토리 디렉토리 경로
                  save_path: Union[str, Path],  # 저장할 최종 영상 파일 경로
                  captions: List,  # 각 페이지 자막 리스트
                  music_path: Union[str, Path],  # 배경 음악 경로
                  num_pages: int,  # 페이지 수
                  fps: int = 10,  # 프레임 수 (초당)
                  audio_sample_rate: int = 16000,  # 오디오 샘플레이트
                  audio_codec: str = "mp3",  # 오디오 코덱
                  caption_config: dict = {},  # 자막 설정
                  fade_duration: float = 1.0,  # 페이드 인/아웃 지속 시간
                  slide_duration: float = 0.4,  # 슬라이드 전환 지속 시간
                  zoom_speed: float = 0.5,  # 줌 효과 속도
                  move_ratio: float = 0.95,  # 이동 효과 확대 비율
                  sound_volume: float = 0.2,  # 효과음 음량
                  music_volume: float = 0.2,  # 배경음악 음량
                  bg_speech_ratio: float = 0.4):  # 배경음과 음성 비율

    if not isinstance(story_dir, Path):
        story_dir = Path(story_dir)  # 문자열이면 Path 객체로 변환

    sound_dir = story_dir / "sound"  # 효과음 디렉토리
    image_dir = story_dir / "image"  # 이미지 디렉토리
    speech_dir = story_dir / "speech"  # 음성 디렉토리

    video_clips = []  # 최종 영상 클립 리스트
    cur_duration = 0  # 현재까지의 누적 시간
    timestamps = []  # 자막 타임스탬프 리스트

    for page in trange(1, num_pages + 1):  # 각 페이지 반복
        # 슬라이드/페이드 구간 무음 처리용 클립 생성
        slide_silence = AudioArrayClip(np.zeros((int(audio_sample_rate * slide_duration), 2)), fps=audio_sample_rate)
        fade_silence = AudioArrayClip(np.zeros((int(audio_sample_rate * fade_duration), 2)), fps=audio_sample_rate)

        if (speech_dir / f"p{page}.wav").exists():  # 단일 음성 파일 존재 시
            single_utterance = True
            speech_file = str(speech_dir / f"./p{page}.wav")
            speech_clip = AudioFileClip(speech_file, fps=audio_sample_rate)
            speech_clip = concatenate_audioclips([fade_silence, speech_clip, fade_silence])
        else:  # 복수 음성 파일인 경우
            single_utterance = False
            speech_files = sorted(speech_dir.glob(f"p{page}_*.wav"), key=lambda x: int(x.stem.split("_")[-1]))
            speech_clips = []

            for utt_idx, speech_file in enumerate(speech_files):
                speech_clip = AudioFileClip(str(speech_file), fps=audio_sample_rate)

                if utt_idx == 0:
                    timestamps.append([cur_duration + fade_duration,
                                       cur_duration + fade_duration + speech_clip.duration])
                    cur_duration += speech_clip.duration + fade_duration
                elif utt_idx == len(speech_files) - 1:
                    timestamps.append([cur_duration,
                                       cur_duration + speech_clip.duration])
                    cur_duration += speech_clip.duration + fade_duration + slide_duration
                else:
                    timestamps.append([cur_duration,
                                       cur_duration + speech_clip.duration])
                    cur_duration += speech_clip.duration

                speech_clips.append(speech_clip)

            speech_clip = concatenate_audioclips([fade_silence] + speech_clips + [fade_silence])
            speech_file = speech_files[0]

        if page == 1:
            speech_clip = concatenate_audioclips([speech_clip, slide_silence])
        else:
            speech_clip = concatenate_audioclips([slide_silence, speech_clip, slide_silence])

        if single_utterance:
            if page == 1:
                timestamps.append([cur_duration + fade_duration,
                                   cur_duration + speech_clip.duration - fade_duration - slide_duration])
                cur_duration += speech_clip.duration - slide_duration
            else:
                timestamps.append([cur_duration + fade_duration + slide_duration,
                                   cur_duration + speech_clip.duration - fade_duration - slide_duration])
                cur_duration += speech_clip.duration - slide_duration

        # 음성 에너지 계산 (배경음 대비 비율 조정용)
        speech_array, _ = librosa.core.load(speech_file, sr=None)
        speech_rms = librosa.feature.rms(y=speech_array)[0].mean()

        # 이미지 클립 설정
        image_file = str(image_dir / f"./p{page}.png")
        image_clip = ImageClip(image_file).set_duration(speech_clip.duration).set_fps(fps)
        image_clip = image_clip.crossfadein(fade_duration).crossfadeout(fade_duration)

        # 이미지에 줌 또는 이동 효과 추가
        if random.random() <= 0.5:
            zoom_mode = "in" if random.random() <= 0.5 else "out"
            image_clip = add_zoom_effect(image_clip, zoom_speed, zoom_mode)
        else:
            direction = "left" if random.random() <= 0.5 else "right"
            image_clip = add_move_effect(image_clip, direction=direction, move_raito=move_ratio)

        # 효과음 처리
        sound_file = sound_dir / f"p{page}.wav"
        if sound_file.exists():
            sound_clip = AudioFileClip(str(sound_file), fps=audio_sample_rate).audio_fadein(fade_duration)
            sound_clip = audio_loop(sound_clip, duration=speech_clip.duration) if sound_clip.duration < speech_clip.duration else sound_clip.subclip(0, speech_clip.duration)
            sound_array, _ = librosa.core.load(str(sound_file), sr=None)
            sound_rms = librosa.feature.rms(y=sound_array)[0].mean()
            ratio = speech_rms / sound_rms * bg_speech_ratio
            audio_clip = CompositeAudioClip([speech_clip, sound_clip.volumex(sound_volume * ratio).audio_fadeout(fade_duration)])
        else:
            audio_clip = speech_clip

        video_clip = image_clip.set_audio(audio_clip)  # 이미지 + 음성 합치기
        video_clips.append(video_clip)

    # 슬라이드 전환 효과 적용
    composite_clip = add_slide_effect(video_clips, slide_duration=slide_duration)

    # 자막 배경 검정 영역 추가
    composite_clip = add_bottom_black_area(composite_clip, black_area_height=caption_config["area_height"])
    del caption_config["area_height"]

    # 자막 삽입
    max_caption_length = caption_config["max_length"]
    del caption_config["max_length"]
    composite_clip = add_caption(
        captions,
        story_dir / "captions.srt",
        timestamps,
        composite_clip,
        max_caption_length,
        **caption_config
    )

    # 배경 음악 추가
    music_clip = AudioFileClip(str(music_path), fps=audio_sample_rate)
    music_array, _ = librosa.core.load(str(music_path), sr=None)
    music_rms = librosa.feature.rms(y=music_array)[0].mean()
    ratio = speech_rms / music_rms * bg_speech_ratio
    music_clip = audio_loop(music_clip, duration=composite_clip.duration) if music_clip.duration < composite_clip.duration else music_clip.subclip(0, composite_clip.duration)

    all_audio_clip = CompositeAudioClip([composite_clip.audio, music_clip.volumex(music_volume * ratio)])
    composite_clip = composite_clip.set_audio(all_audio_clip)

    # 최종 영상 파일로 저장
    composite_clip.write_videofile(str(save_path),
                                   audio_fps=audio_sample_rate,
                                   audio_codec=audio_codec)


@register_tool("slideshow_video_compose")  # 해당 클래스를 "slideshow_video_compose" 도구로 등록
class SlideshowVideoComposeAgent:

    def __init__(self, cfg) -> None:  # 초기화 메서드
        self.cfg = cfg  # 설정 정보를 인스턴스 변수로 저장

    def adjust_caption_config(self, width, height):  # 화면 크기에 맞게 자막 영역 높이 및 폰트 크기 계산
        area_height = int(height * 0.06)  # 영상 높이의 6%를 자막 표시 영역 높이로 설정
        fontsize = int((width + height) / 2 * 0.025)  # 폰트 크기 = 화면 크기의 평균 * 계수
        return {
            "fontsize": fontsize,  # 자막 글자 크기
            "area_height": area_height  # 자막 배경 영역 높이
        }

    def call(self, params):  # 슬라이드쇼 영상 생성을 실행하는 메서드
        height = params["height"]  # 영상 세로 길이
        width = params["width"]  # 영상 가로 길이
        pages = params["pages"]  # 자막(또는 페이지 텍스트) 리스트

        # 자막 설정 업데이트 (화면 크기에 따라 자동 조정)
        params["caption"].update(self.adjust_caption_config(width, height))

        # 영상 제작 함수 호출
        compose_video(
            story_dir=Path(params["story_dir"]),  # 스토리 리소스 디렉토리
            save_path=Path(params["story_dir"]) / "output.mp4",  # 저장 경로는 디렉토리 내 output.mp4
            captions=pages,  # 자막 리스트 전달
            music_path=Path(params["story_dir"]) / "music/music.wav",  # 배경 음악 경로
            num_pages=len(pages),  # 페이지 수
            fps=params["fps"],  # 프레임 수
            audio_sample_rate=params["audio_sample_rate"],  # 오디오 샘플레이트
            audio_codec=params["audio_codec"],  # 오디오 코덱
            caption_config=params["caption"],  # 자막 설정
            **params["slideshow_effect"]  # 줌/이동/페이드 등 슬라이드쇼 효과 설정
        )
