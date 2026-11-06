"""Map original photo EXIF capture times onto a lecture audio recording.

An audio start or end clock time is required for absolute audio offsets. A WAV
file's filesystem timestamps are never treated as recording timestamps.
"""

import argparse
import csv
import json
import struct
import wave
from datetime import datetime, timedelta
from pathlib import Path

from PIL import ExifTags, Image


def parse_clock(value):
    try:
        clock = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("clock time must be YYYY-MM-DD HH:MM:SS[.ffffff]") from exc
    if clock.tzinfo is not None:
        raise ValueError("use the phone's local clock time without a timezone offset")
    return clock


def photo_capture(path):
    with Image.open(path) as image:
        exif = image.getexif()
        detail = exif.get_ifd(ExifTags.IFD.Exif)
        value = detail.get(36867) or exif.get(306)
        subsecond = detail.get(37521)
        make = exif.get(271, "")
        model = exif.get(272, "")
    if not value:
        raise ValueError(f"photo has no EXIF capture time: {path.name}")
    captured = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    if subsecond is not None:
        digits = "".join(char for char in str(subsecond) if char.isdigit())
        if digits:
            captured = captured.replace(microsecond=int((digits + "000000")[:6]))
    return captured, make, model


def wav_chunks(path):
    length = path.stat().st_size
    with path.open("rb") as file:
        if file.read(4) != b"RIFF":
            raise ValueError("audio is not RIFF WAV")
        file.seek(8)
        if file.read(4) != b"WAVE":
            raise ValueError("audio is not WAVE")
        offset = 12
        tags = []
        while offset + 8 <= length:
            file.seek(offset)
            chunk = file.read(8)
            if len(chunk) != 8:
                break
            tag, size = struct.unpack("<4sI", chunk)
            tags.append(tag.decode("ascii", errors="replace"))
            offset += 8 + size + (size % 2)
    return tags


def timecode(seconds):
    milliseconds = round(seconds * 1000)
    sign = "-" if milliseconds < 0 else ""
    milliseconds = abs(milliseconds)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    whole, fraction = divmod(remainder, 1000)
    return f"{sign}{hours:02d}:{minutes:02d}:{whole:02d}.{fraction:03d}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--image-sources", type=Path, default=Path("deliverables_20261106_v3/image_sources.csv"))
    parser.add_argument("--out", type=Path, required=True)
    anchor = parser.add_mutually_exclusive_group()
    anchor.add_argument("--audio-start", help="phone-local clock time, YYYY-MM-DD HH:MM:SS")
    anchor.add_argument("--audio-end", help="phone-local clock time, YYYY-MM-DD HH:MM:SS")
    args = parser.parse_args()
    audio = args.audio.resolve()
    photos = args.photos.resolve()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"output directory is not empty: {out}")
    with wave.open(str(audio), "rb") as file:
        frames = file.getnframes()
        rate = file.getframerate()
        duration = frames / rate
        channels = file.getnchannels()
    with args.image_sources.open(newline="", encoding="utf-8-sig") as file:
        source_rows = list(csv.DictReader(file))
    source_by_name = {row["filename"]: row for row in source_rows}
    if len(source_by_name) != len(source_rows):
        raise ValueError("duplicate filename in image sources")
    paths = list(photos.glob("*.jpg"))
    if set(path.name for path in paths) != set(source_by_name):
        raise ValueError("original photos and selected-image inventory do not match")
    shots = []
    for path in paths:
        captured, make, model = photo_capture(path)
        filename_time = datetime.strptime(path.stem.removeprefix("IMG_"), "%Y%m%d_%H%M%S")
        source = source_by_name[path.name]
        selected = (args.image_sources.resolve().parent / source["selected_image"]).resolve()
        if not selected.is_file():
            raise ValueError(f"selected image is missing: {selected}")
        shots.append({"index": int(source["index"]), "filename": path.name,
                      "captured": captured, "filename_time": filename_time,
                      "make": make, "model": model, "selected_image": str(selected)})
    shots.sort(key=lambda item: item["captured"])
    if len(shots) != 89:
        raise ValueError(f"expected 89 photos, got {len(shots)}")
    if len({(shot["make"], shot["model"]) for shot in shots}) != 1:
        raise ValueError("photos were taken by multiple device models")
    first, last = shots[0]["captured"], shots[-1]["captured"]
    if args.audio_start:
        start = parse_clock(args.audio_start)
        end = start + timedelta(seconds=duration)
        anchor_kind = "recording_start"
    elif args.audio_end:
        end = parse_clock(args.audio_end)
        start = end - timedelta(seconds=duration)
        anchor_kind = "recording_end"
    else:
        start = end = None
        anchor_kind = "missing"
    rows = []
    for number, shot in enumerate(shots):
        captured = shot["captured"]
        next_time = shots[number + 1]["captured"] if number + 1 < len(shots) else None
        offset = (captured - start).total_seconds() if start else None
        if offset is None:
            status = "awaiting_recording_clock"
        elif offset < 0:
            status = "before_recording"
        elif offset > duration:
            status = "after_recording"
        else:
            status = "inside_recording"
        rows.append({
            "photo_index": shot["index"],
            "filename": shot["filename"],
            "capture_time_exif_local": captured.isoformat(sep=" ", timespec="milliseconds"),
            "filename_time_local": shot["filename_time"].isoformat(sep=" "),
            "filename_minus_exif_seconds": round((shot["filename_time"] - captured).total_seconds(), 3),
            "seconds_since_first_photo": round((captured - first).total_seconds(), 3),
            "next_photo_time_exif_local": next_time.isoformat(sep=" ", timespec="milliseconds") if next_time else "",
            "seconds_until_next_photo": round((next_time - captured).total_seconds(), 3) if next_time else "",
            "audio_offset_seconds": round(offset, 3) if offset is not None else "",
            "audio_timecode": timecode(offset) if offset is not None else "",
            "audio_window_end": timecode((next_time - start).total_seconds()) if next_time and start else "",
            "match_status": status,
            "selected_image": shot["selected_image"],
        })
    out.mkdir(parents=True, exist_ok=True)
    with (out / "photo_audio_timeline.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    audio_stat = audio.stat()
    metadata = {
        "audio_file": str(audio), "audio_size_bytes": audio_stat.st_size,
        "audio_frames": frames, "audio_sample_rate_hz": rate, "audio_channels": channels,
        "audio_duration_seconds": duration, "audio_duration_timecode": timecode(duration),
        "wav_chunks": wav_chunks(audio),
        "filesystem_created_time": datetime.fromtimestamp(audio_stat.st_ctime).isoformat(sep=" "),
        "filesystem_modified_time": datetime.fromtimestamp(audio_stat.st_mtime).isoformat(sep=" "),
        "recording_clock_anchor": anchor_kind,
        "recording_start_local": start.isoformat(sep=" ") if start else None,
        "recording_end_local": end.isoformat(sep=" ") if end else None,
        "photo_count": len(shots), "photo_device": f"{shots[0]['make']} {shots[0]['model']}",
        "first_photo_exif_local": first.isoformat(sep=" ", timespec="milliseconds"),
        "last_photo_exif_local": last.isoformat(sep=" ", timespec="milliseconds"),
        "photo_span_seconds": (last - first).total_seconds(),
        "possible_recording_start_earliest_local": (last - timedelta(seconds=duration)).isoformat(sep=" ", timespec="milliseconds"),
        "possible_recording_start_latest_local": first.isoformat(sep=" ", timespec="milliseconds"),
        "photos_inside_recording": sum(row["match_status"] == "inside_recording" for row in rows) if start else None,
    }
    (out / "alignment_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    if start is None:
        message = ("# 等待录音起止时间\n\n"
                   "89 张照片的 EXIF 原始拍摄时间已提取，选用校正版也已关联。"
                   "录音为 68 分 20.240 秒；WAV 只含音频数据，不含录制日期或起止时间。"
                   "电脑上的文件创建时间是转存时间，不能用于对齐。\n\n"
                   "请提供手机录音界面显示的开始时间或结束时间（含日期）。"
                   "得到其中一个时间后即可计算每张照片在录音中的分秒位置。\n")
    else:
        message = (f"# 图片与录音时间轴\n\n录音开始：{start}\n\n录音结束：{end}\n\n"
                   f"录音时长：{timecode(duration)}\n\n89 张照片中，"
                   f"{metadata['photos_inside_recording']} 张落在录音范围内。"
                   "每张图片的对应音频位置见 photo_audio_timeline.csv。"
                   "相邻照片构成的时间窗仅是抽样近似，并不等于实际换页的精确时刻。\n")
    (out / "时间轴说明.md").write_text(message, encoding="utf-8")
    inside = metadata["photos_inside_recording"] if start else "pending"
    print(f"photos={len(rows)} audio={timecode(duration)} anchor={anchor_kind} inside={inside}")
    print(f"first_photo={first} last_photo={last}")


if __name__ == "__main__":
    main()
