import streamlit as st
import subprocess
import tempfile
import os
import numpy as np
import imageio_ffmpeg

st.set_page_config(page_title="CLIPMASTER AI", page_icon="🎬", layout="wide")

st.title("🎬 CLIPMASTER AI")
st.subheader("Long Videos → Best Shorts")

st.write("Upload your gaming video and discover exciting moments.")

video = st.file_uploader("Upload your video", type=["mp4", "mov", "mkv"])

if video:
    st.video(video)

    duration = st.number_input(
        "Clip duration (seconds)",
        min_value=10,
        max_value=60,
        value=30
    )

    number = st.slider("Number of clips", 1, 10, 3)

    if st.button("🚀 FIND BEST MOMENTS"):
        with st.spinner("Analyzing video audio..."):
            try:
                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

                with tempfile.TemporaryDirectory() as folder:
                    source = os.path.join(folder, "input.mp4")

                    with open(source, "wb") as f:
                        f.write(video.getbuffer())

                    command = [
                        ffmpeg, "-i", source,
                        "-vn", "-ac", "1", "-ar", "8000",
                        "-f", "s16le", "-"
                    ]

                    result = subprocess.run(
                        command,
                        capture_output=True,
                        check=True
                    )

                    audio = np.frombuffer(result.stdout, dtype=np.int16)

                    if len(audio) == 0:
                        st.error("Audio not found in this video.")
                    else:
                        samples_per_second = 8000
                        window = samples_per_second

                        scores = []

                        for i in range(0, len(audio), window):
                            part = audio[i:i + window]
                            if len(part):
                                scores.append(
                                    (i / samples_per_second,
                                     float(np.sqrt(np.mean(part.astype(float) ** 2))))
                                )

                        scores.sort(key=lambda x: x[1], reverse=True)

                        selected = []

                        for timestamp, score in scores:
                            start = max(0, timestamp - duration / 2)

                            if all(
                                abs(start - old) >= duration
                                for old in selected
                            ):
                                selected.append(start)

                            if len(selected) >= number:
                                break

                        st.success("Potential highlight moments found!")

                        for index, start in enumerate(selected, 1):
                            output = os.path.join(folder, f"short_{index}.mp4")

                            subprocess.run([
                                ffmpeg, "-y", "-ss", str(start),
                                "-i", source,
                                "-t", str(duration),
                                "-vf",
                                "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                                "-c:v", "libx264",
                                "-preset", "ultrafast",
                                "-c:a", "aac",
                                output
                            ], capture_output=True, check=True)

                            with open(output, "rb") as f:
                                data = f.read()

                            st.write(f"Clip {index} — {int(start)} seconds")
                            st.video(data)

                            st.download_button(
                                f"⬇️ Download Clip {index}",
                                data,
                                file_name=f"clipmaster_{index}.mp4",
                                mime="video/mp4",
                                key=f"download_{index}"
                            )

            except Exception as e:
                st.error(f"Processing error: {e}")

st.caption("Note: Audio peaks suggest exciting moments; they do not guarantee viral clips.")
