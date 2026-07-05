from pathlib import Path


def clean_frame_directory(frames_dir, pattern="frame_*.png"):
    frames_path = Path(frames_dir)
    frames_path.mkdir(parents=True, exist_ok=True)

    removed = 0

    for frame_file in frames_path.glob(pattern):
        if frame_file.is_file():
            frame_file.unlink()
            removed += 1

    return removed
