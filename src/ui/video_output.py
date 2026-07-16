from pathlib import Path

import streamlit as st

from utils.file_size import format_file_size


MAX_INLINE_DOWNLOAD_BYTES = 200 * 1024 * 1024


def show_finished_video(output_file, *, root_dir=None):
    video_path = resolve_video_path(output_file, root_dir=root_dir)
    if video_path is None or not video_path.is_file():
        st.warning(
            f"The rendered video could not be found: {output_file}",
            icon=":material/video_file:",
        )
        return False

    size = video_path.stat().st_size
    st.subheader("Finished video")
    st.video(str(video_path))
    st.caption(f"{format_file_size(size)} · {video_path}")

    if size <= MAX_INLINE_DOWNLOAD_BYTES:
        with video_path.open("rb") as video_file:
            st.download_button(
                "Download MP4",
                data=video_file,
                file_name=video_path.name,
                mime="video/mp4",
                icon=":material/download:",
                width="stretch",
                on_click="ignore",
            )
    else:
        st.info(
            "This video is larger than 200 MB. It is available at the path "
            "shown above, but is not copied into Streamlit memory for download.",
            icon=":material/hard_drive:",
        )

    return True


def resolve_video_path(output_file, *, root_dir=None):
    if not output_file:
        return None

    path = Path(str(output_file)).expanduser()
    if not path.is_absolute() and root_dir is not None:
        path = Path(root_dir) / path
    return path.resolve()
