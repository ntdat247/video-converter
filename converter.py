"""
converter.py - Core Engine for WebM to MP4 conversion using FFmpeg
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple


@dataclass
class MediaInfo:
    duration: float
    width: int
    height: int
    video_codec: str
    audio_codec: Optional[str]
    size_bytes: int
    fps: float


@dataclass
class ConversionProgress:
    percentage: float
    current_time: float
    total_time: float
    speed: str
    fps: float
    eta_seconds: Optional[float]


@dataclass
class ConversionResult:
    success: bool
    input_path: Path
    output_path: Path
    elapsed_time: float
    error_message: Optional[str] = None
    output_size_bytes: int = 0


def format_duration(seconds: float | None) -> str:
    """Format giây thành định dạng HH:MM:SS hoặc MM:SS dễ nhìn."""
    if not seconds or seconds <= 0:
        return "00:00"
    total_sec = int(round(seconds))
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


active_process: Optional[subprocess.Popen] = None
is_paused: bool = False


def pause_conversion() -> bool:
    """Tạm dừng tiến trình FFmpeg bằng tín hiệu SIGSTOP (giải phóng CPU về 0%)."""
    global is_paused
    if active_process and active_process.poll() is None:
        try:
            import signal
            os.kill(active_process.pid, signal.SIGSTOP)
            is_paused = True
            return True
        except Exception:
            pass
    return False


def resume_conversion() -> bool:
    """Tiếp tục tiến trình FFmpeg bằng tín hiệu SIGCONT."""
    global is_paused
    if active_process and active_process.poll() is None:
        try:
            import signal
            os.kill(active_process.pid, signal.SIGCONT)
            is_paused = False
            return True
        except Exception:
            pass
    return False


def stop_conversion() -> bool:
    """Dừng hoàn toàn tiến trình FFmpeg bằng SIGKILL."""
    global is_paused
    if active_process and active_process.poll() is None:
        try:
            import signal
            if is_paused:
                os.kill(active_process.pid, signal.SIGCONT)
            active_process.kill()
            active_process.wait()
            is_paused = False
            return True
        except Exception:
            pass
    return False


def _parse_vint(data: bytes, offset: int) -> Tuple[Optional[int], int]:
    """Parse EBML Variable-length integer (VINT). Trả về (giá trị, số byte đọc được)."""
    if offset >= len(data):
        return None, 0
    first_byte = data[offset]
    for length in range(1, 9):
        mask = 0x80 >> (length - 1)
        if first_byte & mask:
            val = first_byte & (~mask)
            for i in range(1, length):
                if offset + i >= len(data):
                    return None, 0
                val = (val << 8) | data[offset + i]
            return val, length
    return None, 0


def extract_webm_duration(path: Path) -> float:
    """
    Trích xuất thời lượng (seconds) từ file WebM/MKV:
    1. Kiểm tra thẻ Duration (0x4489) trong Segment Info ở header (FFmpeg, Handbrake, v.v.).
    2. Nếu không có (như các file WebM ghi trực tiếp từ Chrome MediaRecorder),
       quét nhanh các Cluster ở cuối file để lấy Timecode lớn nhất.
    """
    try:
        size = path.stat().st_size
        if size < 1024:
            return 0.0

        with open(path, "rb") as f:
            # 1. Đọc header (Segment Info)
            header = f.read(min(size, 8192))
            scale_idx = header.find(b"\x2a\xd7\xb1")
            timecode_scale_ns = 1_000_000  # Mặc định của WebM: 1ms = 1_000_000 ns
            if scale_idx != -1:
                val_len, v_len = _parse_vint(header, scale_idx + 3)
                if val_len and val_len <= 8:
                    raw_val = header[scale_idx + 3 + v_len : scale_idx + 3 + v_len + val_len]
                    if len(raw_val) == val_len:
                        timecode_scale_ns = int.from_bytes(raw_val, "big")

            # Kiểm tra thẻ Duration (ID 0x4489)
            dur_idx = header.find(b"\x44\x89")
            if dur_idx != -1:
                d_len, d_vlen = _parse_vint(header, dur_idx + 2)
                if d_len in (4, 8):
                    raw_dur = header[dur_idx + 2 + d_vlen : dur_idx + 2 + d_vlen + d_len]
                    if len(raw_dur) == d_len:
                        fmt = ">f" if d_len == 4 else ">d"
                        raw_float = struct.unpack(fmt, raw_dur)[0]
                        dur_sec = (raw_float * timecode_scale_ns) / 1_000_000_000.0
                        if dur_sec > 0:
                            return dur_sec

            # 2. Nếu header không có Duration (Chrome WebM recording), đọc 4MB cuối cùng để quét Cluster
            read_size = min(size, 4 * 1024 * 1024)
            f.seek(size - read_size)
            data = f.read(read_size)

        cluster_id = b"\x1f\x43\xb6\x75"
        matches = [i for i in range(len(data)) if data.startswith(cluster_id, i)]
        if not matches:
            return 0.0

        # Quét ngược các cluster cuối để tìm Timecode (ID 0xE7)
        for c_idx in reversed(matches[-20:]):
            chunk = data[c_idx : c_idx + 120]
            offset = 4  # Bỏ qua 4 byte Cluster ID
            _, size_vint_len = _parse_vint(chunk, offset)
            if size_vint_len == 0:
                continue
            offset += size_vint_len

            while offset < len(chunk) - 2:
                elem_id = chunk[offset]
                offset += 1
                if elem_id == 0xE7:  # Timecode element
                    data_len, vint_len = _parse_vint(chunk, offset)
                    if data_len and 1 <= data_len <= 8:
                        tc_bytes = chunk[offset + vint_len : offset + vint_len + data_len]
                        if len(tc_bytes) == data_len:
                            tc = int.from_bytes(tc_bytes, "big")
                            return (tc * timecode_scale_ns) / 1_000_000_000.0
                    break
                elif elem_id in (0xEC, 0xBF):  # Void padding
                    data_len, vint_len = _parse_vint(chunk, offset)
                    if vint_len > 0:
                        offset += vint_len + (data_len or 0)
                    else:
                        break
                else:
                    break
        return 0.0
    except Exception:
        return 0.0


def check_dependencies() -> tuple[bool, str]:
    """Kiểm tra ffmpeg và ffprobe đã có trên hệ thống chưa."""
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    if not ffmpeg_path:
        return False, "Không tìm thấy 'ffmpeg' trên hệ thống. Cài đặt bằng: sudo apt update && sudo apt install -y ffmpeg"
    if not ffprobe_path:
        return False, "Không tìm thấy 'ffprobe' trên hệ thống. Cài đặt bằng: sudo apt update && sudo apt install -y ffmpeg"
    return True, "Sẵn sàng"


def get_media_info(file_path: str | Path) -> MediaInfo:
    """Lấy thông tin media của file thông qua ffprobe và fallback WebM EBML parser."""
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File không tồn tại: {path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration,size,bit_rate:stream=codec_name,codec_type,width,height,r_frame_rate",
        "-of", "json",
        str(path)
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Lỗi khi đọc file bằng ffprobe: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    fmt = data.get("format", {})
    streams = data.get("streams", [])

    duration_val = fmt.get("duration")
    duration = float(duration_val) if duration_val is not None and duration_val != "N/A" else 0.0
    size_bytes = int(fmt.get("size", path.stat().st_size))

    video_codec = "unknown"
    audio_codec = None
    width = 0
    height = 0
    fps = 0.0

    for s in streams:
        c_type = s.get("codec_type")
        if c_type == "video" and video_codec == "unknown":
            video_codec = s.get("codec_name", "unknown")
            width = int(s.get("width", 0))
            height = int(s.get("height", 0))
            r_fps = s.get("r_frame_rate", "0/1")
            try:
                if "/" in r_fps:
                    num, den = r_fps.split("/")
                    fps = float(num) / float(den) if float(den) != 0 else 0.0
                else:
                    fps = float(r_fps)
            except Exception:
                fps = 0.0
        elif c_type == "audio" and audio_codec is None:
            audio_codec = s.get("codec_name")

    # Nếu ffprobe không tìm thấy duration (rất phổ biến ở WebM quay từ Chrome MediaRecorder),
    # dùng EBML cluster parser để lấy chính xác timestamp cuối cùng.
    if duration <= 0.0 and path.suffix.lower() in (".webm", ".mkv"):
        extracted_dur = extract_webm_duration(path)
        if extracted_dur > 0.0:
            duration = extracted_dur

    return MediaInfo(
        duration=duration,
        width=width,
        height=height,
        video_codec=video_codec,
        audio_codec=audio_codec,
        size_bytes=size_bytes,
        fps=fps,
    )


SUPPORTED_FORMATS = {"mp4", "webm", "mov", "mkv"}


def get_default_target_ext(input_path: Path | str) -> str:
    """Xác định đuôi file mặc định dựa trên định dạng nguồn."""
    in_ext = Path(input_path).suffix.lstrip(".").lower()
    if in_ext == "webm":
        return "mp4"
    elif in_ext in ("mov", "mkv"):
        return "mp4"
    elif in_ext == "mp4":
        return "webm"
    return "mp4"


def convert_file(
    input_path: str | Path,
    output_path: Optional[str | Path] = None,
    target_format: Optional[str] = None,
    crf: int = 14,
    preset: str = "slow",
    audio_bitrate: str = "320k",
    copy_streams: bool = False,
    overwrite: bool = True,
    progress_callback: Optional[Callable[[ConversionProgress], None]] = None,
    cancel_event: Optional[Any] = None,
    log_callback: Optional[Callable[[str, str], None]] = None,
) -> ConversionResult:
    """
    Chuyển đổi video linh hoạt giữa các định dạng: WebM <-> MP4 <-> MOV.
    - MP4 / MOV: H.264 video (libx264, yuv420p) + AAC audio + movflags +faststart.
    - WebM: VP9 video (libvpx-vp9, yuv420p) + Opus audio (libopus).
    - copy_streams: Sao chép luồng trực tiếp không cần re-encode (cực nhanh cho MP4 <-> MOV).
    - Progress được stream realtime qua stdout (-progress pipe:1).
    """
    in_path = Path(input_path).resolve()
    if not in_path.is_file():
        target_ext = target_format or "mp4"
        return ConversionResult(
            success=False,
            input_path=in_path,
            output_path=Path(output_path) if output_path else in_path.with_suffix(f".{target_ext}"),
            elapsed_time=0.0,
            error_message=f"File nguồn không tồn tại: {in_path}",
        )

    # Xác định đường dẫn file đầu ra và định dạng đích
    if output_path is None:
        target_ext = (target_format or get_default_target_ext(in_path)).lstrip(".").lower()
        out_path = in_path.with_suffix(f".{target_ext}")
    else:
        out_path = Path(output_path).resolve()
        target_ext = out_path.suffix.lstrip(".").lower()
        if not target_ext and target_format:
            target_ext = target_format.lstrip(".").lower()
            out_path = out_path.with_suffix(f".{target_ext}")

    if not target_ext:
        target_ext = "mp4"

    if out_path == in_path:
        out_path = in_path.parent / f"{in_path.stem}_converted.{target_ext}"

    if out_path.exists() and not overwrite:
        return ConversionResult(
            success=False,
            input_path=in_path,
            output_path=out_path,
            elapsed_time=0.0,
            error_message=f"File đầu ra đã tồn tại và cờ overwrite=False: {out_path}",
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        info = get_media_info(in_path)
    except Exception as e:
        return ConversionResult(
            success=False,
            input_path=in_path,
            output_path=out_path,
            elapsed_time=0.0,
            error_message=f"Không đọc được thông tin video: {e}",
        )

    total_duration = info.duration
    has_known_duration = total_duration > 0.0

    cmd = [
        "ffmpeg",
        "-y" if overwrite else "-n",
        "-i", str(in_path),
    ]

    if copy_streams:
        cmd.extend(["-c", "copy"])
        if target_ext in ("mp4", "mov"):
            cmd.extend(["-movflags", "+faststart"])
    else:
        if target_ext in ("mp4", "mov", "mkv"):
            cmd.extend([
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", str(crf),
                "-preset", str(preset),
            ])
            if info.audio_codec is not None:
                cmd.extend(["-c:a", "aac", "-b:a", str(audio_bitrate)])
            else:
                cmd.extend(["-an"])

            if target_ext in ("mp4", "mov"):
                cmd.extend(["-movflags", "+faststart"])

        elif target_ext == "webm":
            cmd.extend([
                "-c:v", "libvpx-vp9",
                "-pix_fmt", "yuv420p",
                "-crf", str(crf),
                "-b:v", "0",
            ])
            # Tối ưu tốc độ encoder VP9 theo preset
            cpu_used = "1" if preset in ("slow", "slower", "veryslow") else ("4" if "fast" in preset else "2")
            cmd.extend(["-cpu-used", cpu_used])

            if info.audio_codec is not None:
                cmd.extend(["-c:a", "libopus", "-b:a", "192k"])
            else:
                cmd.extend(["-an"])
        else:
            # Fallback cho định dạng khác
            cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf)])
            if info.audio_codec is not None:
                cmd.extend(["-c:a", "aac", "-b:a", str(audio_bitrate)])
            else:
                cmd.extend(["-an"])

    cmd.extend([
        "-nostats",
        "-loglevel", "warning",
        "-progress", "pipe:1",
        str(out_path)
    ])

    start_time = time.time()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    global active_process, is_paused
    active_process = proc
    is_paused = False

    current_speed = "0x"
    current_fps = 0.0

    if log_callback:
        log_callback("INFO", f"Bắt đầu chuyển đổi: {in_path.name}")
        log_callback("INFO", f"Video gốc: {info.width}x{info.height}, Thời lượng: {format_duration(info.duration)}, Codec: {info.video_codec}/{info.audio_codec or 'None'}")
        log_callback("INFO", f"Cấu hình xuất: {out_path.name} | {'Stream Copy' if copy_streams else f'Codec: {target_ext}, CRF: {crf}, Preset: {preset}'}")

    # Thread tiêu thụ stderr liên tục tránh tràn bộ đệm pipe OS (64KB deadlock trên Linux)
    stderr_lines: list[str] = []

    def drain_stderr():
        if proc.stderr:
            for el in proc.stderr:
                stderr_lines.append(el)
                if len(stderr_lines) > 300:
                    stderr_lines.pop(0)
                el_strip = el.strip()
                if el_strip and log_callback:
                    low = el_strip.lower()
                    lvl = "ERROR" if "error" in low else ("WARN" if "warning" in low else "DEBUG")
                    log_callback(lvl, el_strip)

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()

    last_debug_log = 0.0

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if cancel_event and hasattr(cancel_event, "is_set") and cancel_event.is_set():
                proc.kill()
                proc.wait()
                if out_path.exists():
                    try:
                        out_path.unlink()
                    except OSError:
                        pass
                return ConversionResult(
                    success=False,
                    input_path=in_path,
                    output_path=out_path,
                    elapsed_time=time.time() - start_time,
                    error_message="Quá trình chuyển đổi đã bị dừng lại bởi người dùng",
                )

            line = line.strip()
            if not line:
                continue

            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()

                if key == "fps":
                    try:
                        current_fps = float(val)
                    except ValueError:
                        pass
                elif key == "speed":
                    current_speed = val
                elif key == "out_time_us":
                    try:
                        curr_sec = float(val) / 1_000_000.0
                        elapsed = time.time() - start_time

                        if has_known_duration:
                            pct = min(99.9, max(0.0, (curr_sec / total_duration) * 100.0))
                            if pct > 0:
                                eta = (elapsed / (pct / 100.0)) - elapsed
                            else:
                                eta = None
                        else:
                            pct = 0.0
                            eta = None

                        if progress_callback:
                            prog = ConversionProgress(
                                percentage=round(pct, 1),
                                current_time=round(curr_sec, 2),
                                total_time=round(total_duration, 2),
                                speed=current_speed,
                                fps=current_fps,
                                eta_seconds=round(eta, 1) if eta and eta > 0 else None,
                            )
                            progress_callback(prog)

                        now_t = time.time()
                        if log_callback and (now_t - last_debug_log >= 3.0):
                            last_debug_log = now_t
                            eta_txt = format_duration(eta) if eta and eta > 0 else "--:--"
                            log_callback("DEBUG", f"Tiến trình: {pct:.1f}% ({format_duration(curr_sec)} / {format_duration(total_duration)}) | Tốc độ: {current_speed} | {current_fps:.0f} fps | ETA: {eta_txt}")
                    except ValueError:
                        pass
                elif key == "progress" and val == "end":
                    if progress_callback:
                        prog = ConversionProgress(
                            percentage=100.0,
                            current_time=round(total_duration if has_known_duration else curr_sec, 2),
                            total_time=round(total_duration, 2),
                            speed=current_speed,
                            fps=current_fps,
                            eta_seconds=0.0,
                        )
                        progress_callback(prog)

        proc.wait()
        stderr_thread.join(timeout=1.0)
        try:
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
        except Exception:
            pass
        stderr_output = "".join(stderr_lines)

        if proc.returncode != 0:
            if out_path.exists():
                try:
                    out_path.unlink()
                except OSError:
                    pass
            err_msg = f"FFmpeg gặp lỗi (code {proc.returncode}): {stderr_output.strip()[-500:]}"
            if log_callback:
                log_callback("ERROR", err_msg)
            return ConversionResult(
                success=False,
                input_path=in_path,
                output_path=out_path,
                elapsed_time=time.time() - start_time,
                error_message=err_msg,
            )

        elapsed = time.time() - start_time
        out_size = out_path.stat().st_size if out_path.exists() else 0

        if log_callback:
            log_callback("INFO", f"Hoàn tất thành công: {out_path.name} | Thời gian: {elapsed:.1f}s")

        return ConversionResult(
            success=True,
            input_path=in_path,
            output_path=out_path,
            elapsed_time=round(elapsed, 2),
            output_size_bytes=out_size,
        )

    except KeyboardInterrupt:
        proc.kill()
        proc.wait()
        if out_path.exists():
            try:
                out_path.unlink()
            except OSError:
                pass
        raise
    except Exception as e:
        proc.kill()
        proc.wait()
        return ConversionResult(
            success=False,
            input_path=in_path,
            output_path=out_path,
            elapsed_time=time.time() - start_time,
            error_message=str(e),
        )
    finally:
        active_process = None
        is_paused = False
