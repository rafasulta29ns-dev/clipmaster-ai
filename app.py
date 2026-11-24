import os
import shutil
import tempfile
from datetime import datetime
import streamlit as st
from processor import (
    check_ffmpeg,
    get_video_info,
    detect_highlights,
    render_vertical_clip,
    capture_authorized_stream_sample,
)

st.set_page_config(
    page_title="CLIPMASTER AI — Gaming Viral Clip Studio",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BASE_DIR = os.path.join(tempfile.gettempdir(), "clipmaster_ai_storage")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
CLIPS_DIR = os.path.join(BASE_DIR, "clips")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CLIPS_DIR, exist_ok=True)

MAX_UPLOAD_MB = 300

defaults = {
    "status": "Waiting",
    "video_path": None,
    "video_name": None,
    "video_info": None,
    "highlights": [],
    "generated_clips": [],
    "history": [],
    "settings": {
        "default_duration": 30,
        "default_num_clips": 5,
        "layout_mode": "blurred_bg",
        "resolution": "720x1280",
        "fps": 30,
    },
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

st.markdown(
    """
    <style>
    .stApp {
        background-color: #090d16;
        color: #f1f5f9;
    }
    .brand-header {
        background: linear-gradient(135deg, #111827 0%, #1e1b4b 100%);
        border: 1px solid #312e81;
        border-radius: 16px;
        padding: 16px 20px;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 10px;
    }
    .brand-title {
        font-size: 1.55rem;
        font-weight: 800;
        background: linear-gradient(90deg, #38bdf8, #a855f7, #f43f5e);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    .status-pill {
        padding: 6px 14px;
        border-radius: 999px;
        font-weight: 700;
        font-size: 0.85rem;
        background: #1e293b;
        border: 1px solid #38bdf8;
        color: #38bdf8;
    }
    .highlight-card {
        background: #111827;
        border: 1px solid #1f2937;
        border-left: 4px solid #8b5cf6;
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 12px;
    }
    .stButton > button {
        width: 100%;
        min-height: 48px;
        border-radius: 12px;
        font-weight: 700;
        font-size: 1rem;
    }
    .stDownloadButton > button {
        width: 100%;
        min-height: 48px;
        border-radius: 12px;
        font-weight: 700;
        background: linear-gradient(90deg, #10b981, #059669);
        color: white;
        border: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

status_emoji = {
    "Waiting": "⏳",
    "Processing": "⚙️",
    "Highlights Found": "🎯",
    "Clips Generated": "🎬",
    "Completed": "✅",
    "Failed": "❌",
}.get(st.session_state.status, "⏳")

st.markdown(
    f"""
    <div class="brand-header">
        <div>
            <div class="brand-title">🎮 CLIPMASTER AI</div>
            <div style="font-size: 0.85rem; color: #94a3b8;">
                Free Mobile-First Gaming Highlight & 9:16 Shorts Studio (Stage 1)
            </div>
        </div>
        <div class="status-pill">{status_emoji} Status: {st.session_state.status}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not check_ffmpeg():
    st.error(
        "FFmpeg is not installed on this server. Make sure `packages.txt` contains `ffmpeg`."
    )
    st.stop()

tabs = st.tabs(
    [
        "📤 Upload & AI Detect",
        "🎬 My Clips",
        "📡 Live Stream",
        "📜 History",
        "⚙️ Settings",
    ]
)

with tabs[0]:
    st.subheader("1. Upload Gameplay Video")
    st.caption(
        f"Supported: MP4, MOV, WEBM • Max safe size on free hosting: **{MAX_UPLOAD_MB} MB**"
    )

    uploaded_file = st.file_uploader(
        "Select video from Android Gallery or Computer",
        type=["mp4", "mov", "webm"],
        help="Choose a recorded gameplay video to analyze for exciting moments.",
    )

    if uploaded_file is not None:
        file_size_mb = uploaded_file.size / (1024 * 1024)
        if file_size_mb > MAX_UPLOAD_MB:
            st.session_state.status = "Failed"
            st.error(
                f"File size ({file_size_mb:.1f} MB) exceeds the {MAX_UPLOAD_MB} MB free-hosting limit. Please trim or compress the video first."
            )
        else:
            save_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
            if st.session_state.video_path != save_path:
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                try:
                    info = get_video_info(save_path)
                    st.session_state.video_path = save_path
                    st.session_state.video_name = uploaded_file.name
                    st.session_state.video_info = info
                    st.session_state.highlights = []
                    st.session_state.status = "Waiting"
                except Exception as e:
                    st.session_state.status = "Failed"
                    st.error(f"Invalid video file: {e}")

    if st.session_state.video_info and st.session_state.video_path:
        info = st.session_state.video_info
        c1, c2, c3 = st.columns(3)
        c1.metric("File", st.session_state.video_name[:18])
        c2.metric("Duration", f"{info['duration']:.1f}s")
        c3.metric("Resolution", f"{info['width']}x{info['height']}")

        st.divider()
        st.subheader("2. Highlight & Clip Preferences")

        col_a, col_b = st.columns(2)
        with col_a:
            preset_choice = st.selectbox(
                "Number of Highlights",
                options=["Best 3 Highlights", "Best 5 Highlights", "Best 10 Highlights", "Custom"],
                index=1,
            )
            if preset_choice == "Best 3 Highlights":
                num_clips = 3
            elif preset_choice == "Best 5 Highlights":
                num_clips = 5
            elif preset_choice == "Best 10 Highlights":
                num_clips = 10
            else:
                num_clips = st.number_input("Custom Clip Count", min_value=1, max_value=15, value=4)

        with col_b:
            dur_choice = st.selectbox(
                "Preferred Clip Duration",
                options=["15 seconds", "30 seconds", "45 seconds", "60 seconds", "Custom"],
                index=1,
            )
            if dur_choice == "Custom":
                clip_duration = st.number_input("Custom Duration (sec)", min_value=5, max_value=90, value=25)
            else:
                clip_duration = int(dur_choice.split()[0])

        if st.button("🚀 Start Automatic Highlight Detection", type="primary"):
            st.session_state.status = "Processing"
            progress_bar = st.progress(0.05, text="Starting audio & frame analysis...")
            try:
                highlights = detect_highlights(
                    st.session_state.video_path,
                    num_clips=int(num_clips),
                    clip_duration=int(clip_duration),
                    progress_callback=lambda p, msg: progress_bar.progress(p, text=msg),
                )
                st.session_state.highlights = highlights
                st.session_state.status = "Highlights Found"
                st.session_state.history.append(
                    {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "video": st.session_state.video_name,
                        "action": f"Detected {len(highlights)} highlights",
                        "status": "Highlights Found",
                    }
                )
                st.rerun()
            except Exception as e:
                st.session_state.status = "Failed"
                st.error(f"Highlight detection failed: {e}")

    if st.session_state.highlights:
        st.divider()
        st.subheader("3. Review & Customize Detected Highlights")
        st.info(
            "Stage 1 uses Audio Spike + Visual Scene-Change detection. You can fine-tune start/end timestamps before cutting."
        )

        max_dur = float(st.session_state.video_info["duration"])
        updated_highlights = []

        for idx, h in enumerate(st.session_state.highlights):
            st.markdown(
                f"""
                <div class="highlight-card">
                    <b>#{h['id']} • {h['category']}</b>
                    <span style="float:right; color:#38bdf8; font-weight:700;">Confidence: {h['confidence']}%</span>
                    <div style="font-size:0.85rem; color:#94a3b8; margin-top:4px;">{h['reason']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            sc1, sc2, sc3 = st.columns([2, 2, 1.5])
            with sc1:
                new_start = st.number_input(
                    f"Start (s) #{h['id']}",
                    min_value=0.0,
                    max_value=max(0.0, max_dur - 1.0),
                    value=float(h["start"]),
                    step=0.5,
                    key=f"start_{idx}",
                )
            with sc2:
                new_end = st.number_input(
                    f"End (s) #{h['id']}",
                    min_value=min(max_dur, new_start + 1.0),
                    max_value=max_dur,
                    value=min(max_dur, max(float(h["end"]), new_start + 1.0)),
                    step=0.5,
                    key=f"end_{idx}",
                )
            with sc3:
                keep = st.checkbox("Include", value=
