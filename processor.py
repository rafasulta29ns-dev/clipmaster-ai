import os
import json
import subprocess
import numpy as np
import cv2


def check_ffmpeg() -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return True
    except Exception:
        return False


def get_video_info(video_path: str) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError("Could not read video metadata. File may be corrupted or unsupported.")

    data = json.loads(result.stdout)
    duration = float(data.get("format", {}).get("duration", 0.0))
    width, height = 1920, 1080
    has_audio = False

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            width = int(stream.get("width", 1920))
            height = int(stream.get("height", 1080))
        elif stream.get("codec_type") == "audio":
            has_audio = True

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "has_audio": has_audio,
    }


def extract_audio_energy_per_second(video_path: str, duration: float) -> np.ndarray:
    sec_count = max(1, int(np.ceil(duration)))
    cmd = [
        "ffmpeg",
        "-i",
        video_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
        "-",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0 or len(proc.stdout) == 0:
        return np.zeros(sec_count, dtype=np.float32)

    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)
    sr = 16000
    energies = np.zeros(sec_count, dtype=np.float32)

    for s in range(sec_count):
        chunk = samples[s * sr : (s + 1) * sr]
        if len(chunk) > 0:
            energies[s] = float(np.sqrt(np.mean(chunk ** 2)))

    max_val = np.max(energies)
    if max_val > 0:
        energies = energies / max_val
    return energies


def extract_visual_motion_per_second(video_path: str, duration: float) -> np.ndarray:
    sec_count = max(1, int(np.ceil(duration)))
    motion = np.zeros(sec_count, dtype=np.float32)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return motion

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    prev_gray = None

    for s in range(sec_count):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(s * fps))
        ret, frame = cap.read()
        if not ret:
            break
        small = cv2.resize(frame, (160, 90))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            motion[s] = float(np.mean(diff))
        prev_gray = gray

    cap.release()
    max_val = np.max(motion)
    if max_val > 0:
        motion = motion / max_val
    return motion


def detect_highlights(
    video_path: str,
    num_clips: int = 5,
    clip_duration: int = 30,
    progress_callback=None,
) -> list:
    info = get_video_info(video_path)
    duration = info["duration"]

    if duration < 5:
        raise ValueError("Video is too short (minimum 5 seconds required).")

    effective_clip_len = min(float(clip_duration), duration)

    if progress_callback:
        progress_callback(0.25, "Analyzing audio intensity & sudden sound peaks...")
    audio_scores = (
        extract_audio_energy_per_second(video_path, duration)
        if info["has_audio"]
        else np.zeros(max(1, int(np.ceil(duration))), dtype=np.float32)
    )

    if progress_callback:
        progress_callback(0.55, "Scanning frames for intense visual action & scene changes...")
    visual_scores = extract_visual_motion_per_second(video_path, duration)

    length = min(len(audio_scores), len(visual_scores))
    audio_scores = audio_scores[:length]
    visual_scores = visual_scores[:length]

    if info["has_audio"] and np.max(audio_scores) > 0:
        combined = 0.6 * audio_scores + 0.4 * visual_scores
    else:
        combined = visual_scores

    if progress_callback:
        progress_callback(0.80, "Ranking top non-overlapping gaming moments...")

    candidate_indices = np.argsort(combined)[::-1]
    selected = []
    min_gap = max(effective_clip_len * 0.75, 8.0)

    for idx in candidate_indices:
        peak_sec = float(idx)
        start_time = max(0.0, peak_sec - (effective_clip_len * 0.35))
        end_time = min(duration, start_time + effective_clip_len)
        if end_time - start_time < effective_clip_len:
            start_time = max(0.0, end_time - effective_clip_len)

        if any(abs(start_time - s["start"]) < min_gap for s in selected):
            continue

        a_val = float(audio_scores[idx]) if idx < len(audio_scores) else 0.0
        v_val = float(visual_scores[idx]) if idx < len(visual_scores) else 0.0
        conf = int(min(98, max(45, round(combined[idx] * 100))))

        if a_val > 0.75 and v_val > 0.65:
            category = "Possible Intense Battle / Reaction"
            reason = "High audio spike paired with rapid visual screen movement."
        elif a_val > 0.70:
            category = "Possible Exciting Reaction / Loud Event"
            reason = "Strong sudden audio peak detected (shouting, gunfire, or celebration)."
        elif v_val > 0.70:
            category = "Possible Fast Gameplay Action"
            reason = "High frame-to-frame motion and scene change detected."
        else:
            category = "Possible Gameplay Moment"
            reason = "Above-average combined audio-visual activity."

        selected.append(
            {
                "id": len(selected) + 1,
                "start": round(start_time, 1),
                "end": round(end_time, 1),
                "duration": round(end_time - start_time, 1),
                "category": category,
                "confidence": conf,
                "reason": reason,
                "selected": True,
            }
        )

        if len(selected) >= num_clips:
            break

    selected.sort(key=lambda x: x["start"])
    for i, item in enumerate(selected, start=1):
        item["id"] = i

    if progress_callback:
        progress_callback(1.0, "Highlight analysis complete!")

    return selected


def render_vertical_clip(
    input_path: str,
    output_path: str,
    start_time: float,
    end_time: float,
    layout_mode: str = "blurred_bg",
    resolution: str = "720x1280",
    fps: int = 30,
) -> str:
    duration = max(1.0, float(end_time) - float(start_time))
    out_w, out_h = map(int, resolution.split("x"))

    if layout_mode == "smart_crop":
        vf = (
            f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"
            f"scale={out_w}:{out_h}:flags=lanczos"
        )
    else:
        vf = (
            f"split[bg][fg];"
            f"[bg]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},boxblur=20:5[bg_blur];"
            f"[fg]scale={out_w}:-2:force_original_aspect_ratio=decrease[fg_scaled];"
            f"[bg_blur][fg_scaled]overlay=(W-w)/2:(H-h)/2"
        )

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_time),
        "-i",
        input_path,
        "-t",
        str(duration),
        "-vf",
        vf,
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        output_path,
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(f"FFmpeg rendering error: {proc.stderr[-300:]}")

    return output_path


def capture_authorized_stream_sample(
    stream_url: str,
    output_path: str,
    capture_seconds: int = 30,
) -> str:
    if not stream_url.startswith(("http://", "https://", "rtmp://")):
        raise ValueError("Invalid stream URL. Must start with http://, https://, or rtmp://")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        stream_url,
        "-t",
        str(capture_seconds),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        output_path,
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
    if proc.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(
            "Could not capture stream. Platforms like YouTube/Twitch require an authorized direct HLS/RTMP relay URL."
        )
    return output_path
