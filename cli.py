#!/usr/bin/env python3
"""
cli.py - Giao diện dòng lệnh chuyển đổi video đa định dạng (WebM, MP4, MOV, MKV)
Hỗ trợ chuyển đổi từng file hoặc hàng loạt thư mục với thanh tiến độ realtime.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

# Import core engine
from converter import (
    ConversionProgress,
    ConversionResult,
    SUPPORTED_FORMATS,
    check_dependencies,
    convert_file,
    get_default_target_ext,
    get_media_info,
)

# Kiểm tra thư viện rich để hiển thị giao diện đẹp
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table

    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None


def format_size(size_bytes: int) -> str:
    """Format bytes thành chuỗi dung lượng dễ đọc."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


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


def print_info(msg: str) -> None:
    if HAS_RICH:
        console.print(f"[bold cyan]ℹ[/bold cyan] {msg}")
    else:
        print(f"[*] {msg}")


def print_success(msg: str) -> None:
    if HAS_RICH:
        console.print(f"[bold green]✔[/bold green] {msg}")
    else:
        print(f"[+] {msg}")


def print_error(msg: str) -> None:
    if HAS_RICH:
        console.print(f"[bold red]✘[/bold red] {msg}", file=sys.stderr)
    else:
        print(f"[-] {msg}", file=sys.stderr)


def collect_video_files(dir_path: Path, recursive: bool = False, from_ext: Optional[str] = None) -> List[Path]:
    """Tìm tất cả các file video hợp lệ trong thư mục."""
    if from_ext:
        exts = [from_ext.lstrip(".").lower()]
    else:
        exts = ["webm", "mp4", "mov", "mkv"]

    matched: List[Path] = []
    for ext in exts:
        pattern = f"**/*.{ext}" if recursive else f"*.{ext}"
        matched.extend(dir_path.glob(pattern))

    return sorted([f for f in matched if f.is_file()])


def process_single_file(
    input_file: Path,
    output_file: Path | None,
    target_format: Optional[str],
    crf: int,
    preset: str,
    audio_bitrate: str,
    copy_streams: bool,
    overwrite: bool,
    delete_original: bool,
) -> ConversionResult:
    """Chuyển đổi một file đơn với thanh tiến độ."""
    # Xác định đuôi đích
    if output_file and output_file.suffix:
        target_ext = output_file.suffix.lstrip(".").lower()
    else:
        target_ext = (target_format or get_default_target_ext(input_file)).lstrip(".").lower()

    if output_file is None:
        output_file = input_file.with_suffix(f".{target_ext}")
        if output_file == input_file:
            output_file = input_file.parent / f"{input_file.stem}_converted.{target_ext}"

    try:
        media_info = get_media_info(input_file)
    except Exception as e:
        print_error(f"Không thể phân tích file {input_file.name}: {e}")
        return ConversionResult(
            success=False,
            input_path=input_file,
            output_path=output_file,
            elapsed_time=0.0,
            error_message=str(e),
        )

    # Mô tả codec đầu ra
    if copy_streams:
        target_video_desc = f"{media_info.video_codec} -> Copy (không encode)"
        target_audio_desc = f"{media_info.audio_codec or 'Không'} -> Copy"
    elif target_ext == "webm":
        target_video_desc = f"{media_info.video_codec} -> vp9 (CRF {crf})"
        target_audio_desc = f"{media_info.audio_codec or 'Không có'} -> libopus (192k)"
    else:
        target_video_desc = f"{media_info.video_codec} -> h264 (CRF {crf})"
        target_audio_desc = f"{media_info.audio_codec or 'Không có'} -> aac ({audio_bitrate})"

    if HAS_RICH:
        info_table = Table(show_header=False, box=None, padding=(0, 2))
        info_table.add_column("Key", style="bold yellow")
        info_table.add_column("Value", style="cyan")
        info_table.add_row("Tên file nguồn:", input_file.name)
        info_table.add_row("Đích đến:", f"{output_file.name} (.{target_ext})")
        info_table.add_row("Dung lượng gốc:", format_size(media_info.size_bytes))
        dur_str = f"{format_duration(media_info.duration)} ({media_info.duration:.1f}s)" if media_info.duration > 0 else "Không xác định (Stream)"
        info_table.add_row("Thời lượng:", dur_str)
        info_table.add_row("Độ phân giải:", f"{media_info.width}x{media_info.height}")
        info_table.add_row("Video Codec:", target_video_desc)
        info_table.add_row("Audio Codec:", target_audio_desc)
        console.print(Panel(info_table, title="[bold green]Thông tin Video[/bold green]", expand=False))

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            TaskProgressColumn(),
            TextColumn("• [cyan]{task.fields[speed]}[/cyan]"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Đang chuyển đổi...", total=100, speed="--")

            def on_progress(p: ConversionProgress) -> None:
                if p.total_time > 0:
                    desc = f"Đang xử lý {format_duration(p.current_time)} / {format_duration(p.total_time)}"
                    completed = p.percentage
                else:
                    desc = f"Đang xử lý {format_duration(p.current_time)}"
                    completed = 0.0

                progress.update(
                    task,
                    completed=completed,
                    speed=f"{p.speed} ({p.fps:.1f} fps)",
                    description=desc,
                )

            res = convert_file(
                input_path=input_file,
                output_path=output_file,
                target_format=target_ext,
                crf=crf,
                preset=preset,
                audio_bitrate=audio_bitrate,
                copy_streams=copy_streams,
                overwrite=overwrite,
                progress_callback=on_progress,
            )
    else:
        print(f"Bắt đầu chuyển đổi: {input_file.name} -> {output_file.name}...")

        def on_progress_simple(p: ConversionProgress) -> None:
            if p.total_time > 0:
                time_str = f"{format_duration(p.current_time)} / {format_duration(p.total_time)} ({p.percentage:.1f}%)"
            else:
                time_str = f"{format_duration(p.current_time)}"
            eta_str = f"ETA: {format_duration(p.eta_seconds)}" if p.eta_seconds else "ETA: --:--"
            sys.stdout.write(f"\rTiến độ: {time_str} [{p.speed}] {eta_str}")
            sys.stdout.flush()

        res = convert_file(
            input_path=input_file,
            output_path=output_file,
            target_format=target_ext,
            crf=crf,
            preset=preset,
            audio_bitrate=audio_bitrate,
            copy_streams=copy_streams,
            overwrite=overwrite,
            progress_callback=on_progress_simple,
        )
        print()

    if res.success:
        orig_size = input_file.stat().st_size
        new_size = res.output_size_bytes
        ratio = (new_size / orig_size * 100.0) if orig_size > 0 else 100.0

        msg = (
            f"Chuyển đổi thành công: {res.output_path.name}\n"
            f"  - Dung lượng: {format_size(orig_size)} -> {format_size(new_size)} ({ratio:.1f}%)\n"
            f"  - Thời gian xử lý: {res.elapsed_time}s"
        )
        print_success(msg)

        if delete_original:
            try:
                input_file.unlink()
                print_info(f"Đã xoá file nguồn gốc: {input_file.name}")
            except OSError as e:
                print_error(f"Không thể xoá file nguồn: {e}")
    else:
        print_error(f"Thất bại: {res.error_message}")

    return res


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ứng dụng chuyển đổi video đa năng (WebM, MP4, MOV) chất lượng cao bằng Python & FFmpeg trên Linux, Windows & macOS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ sử dụng:
  # Chuyển đổi WebM sang MP4 (mặc định):
  vid video.webm
  vid video.webm -o ket_qua.mp4

  # Chuyển đổi MP4 sang WebM:
  vid video.mp4
  vid video.mp4 -t webm

  # Chuyển đổi qua lại giữa MP4 và MOV:
  vid video.mp4 -t mov
  vid video.mov -t mp4

  # Sao chép luồng trực tiếp không nén lại (cực nhanh <1s cho MP4 <-> MOV):
  vid video.mp4 -t mov --copy
  vid video.mov -t mp4 --copy

  # Chuyển đổi toàn bộ thư mục:
  vid -d /path/to/folder -t mp4
  vid -d /path/to/folder --from mov --to mp4
        """,
    )

    parser.add_argument(
        "input",
        nargs="?",
        type=str,
        help="Đường dẫn file video hoặc thư mục chứa file video (WebM, MP4, MOV, MKV)",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Đường dẫn file đầu ra hoặc thư mục đầu ra",
    )
    parser.add_argument(
        "-t", "--to",
        type=str,
        choices=["mp4", "webm", "mov", "mkv"],
        help="Định dạng video đầu ra mong muốn (mặc định: tự động xác định từ nguồn hoặc đích)",
    )
    parser.add_argument(
        "--from",
        dest="from_format",
        type=str,
        choices=["webm", "mp4", "mov", "mkv"],
        help="Lọc định dạng video nguồn khi quét thư mục",
    )
    parser.add_argument(
        "-d", "--dir",
        type=str,
        help="Thư mục chứa các file video cần chuyển đổi hàng loạt",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Tìm kiếm file video trong tất cả các thư mục con",
    )
    parser.add_argument(
        "-c", "--copy",
        action="store_true",
        help="Sao chép trực tiếp stream không mã hóa lại (remux copy, cực nhanh cho MP4 <-> MOV)",
    )
    parser.add_argument(
        "-q", "--crf",
        type=int,
        default=14,
        help="Chỉ số CRF chất lượng video (0-51, mặc định 14 cho độ nét tối đa. Càng nhỏ video càng đẹp nhưng file càng nặng)",
    )
    parser.add_argument(
        "-p", "--preset",
        type=str,
        default="slow",
        choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
        help="Tốc độ mã hóa H.264 / VP9 (mặc định: slow)",
    )
    parser.add_argument(
        "-b", "--audio-bitrate",
        type=str,
        default="320k",
        help="Bitrate âm thanh AAC (mặc định: 320k cho MP4/MOV, 192k cho WebM Opus)",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Tự động ghi đè nếu file đầu ra đã tồn tại",
    )
    parser.add_argument(
        "--delete-original",
        action="store_true",
        help="Xóa file gốc sau khi chuyển đổi thành công",
    )
    parser.add_argument(
        "-g", "--gui",
        action="store_true",
        help="Khởi chạy giao diện đồ họa Web GUI trực quan",
    )

    args = parser.parse_args()

    # Khởi chạy giao diện đồ họa nếu có cờ --gui
    if args.gui:
        from app_gui import run_gui
        run_gui()
        sys.exit(0)

    # 1. Kiểm tra môi trường ffmpeg
    ready, msg = check_dependencies()
    if not ready:
        print_error(msg)
        sys.exit(1)

    # 2. Xác định chế độ chạy (đơn file hay thư mục)
    dir_target = args.dir
    single_target = args.input

    # Nếu người dùng truyền đường dẫn vào vị trí input nhưng đó là thư mục
    if single_target and Path(single_target).is_dir() and not dir_target:
        dir_target = single_target
        single_target = None

    if not dir_target and not single_target:
        parser.print_help()
        print_error("\nVui lòng chỉ định file video hoặc thư mục cần chuyển đổi!")
        sys.exit(1)

    # Chế độ chuyển đổi hàng loạt (Directory mode)
    if dir_target:
        target_path = Path(dir_target).resolve()
        if not target_path.is_dir():
            print_error(f"Thư mục không tồn tại: {target_path}")
            sys.exit(1)

        video_files = collect_video_files(target_path, recursive=args.recursive, from_ext=args.from_format)
        if not video_files:
            filter_msg = f" định dạng {args.from_format}" if args.from_format else ""
            print_info(f"Không tìm thấy file video{filter_msg} nào trong thư mục: {target_path}")
            sys.exit(0)

        out_dir = Path(args.output).resolve() if args.output else target_path
        out_dir.mkdir(parents=True, exist_ok=True)

        print_info(f"Tìm thấy {len(video_files)} file video cần xử lý trong: {target_path}")
        print_info(f"Thư mục lưu kết quả: {out_dir}\n")

        results: List[ConversionResult] = []
        for idx, file_path in enumerate(video_files, start=1):
            target_ext = (args.to or get_default_target_ext(file_path)).lstrip(".").lower()
            if HAS_RICH:
                console.rule(f"[bold cyan]File {idx}/{len(video_files)}: {file_path.name} -> .{target_ext}[/bold cyan]")
            else:
                print(f"\n--- [{idx}/{len(video_files)}] {file_path.name} -> .{target_ext} ---")

            if args.recursive:
                rel_path = file_path.relative_to(target_path)
                curr_out = (out_dir / rel_path).with_suffix(f".{target_ext}")
            else:
                curr_out = (out_dir / file_path.name).with_suffix(f".{target_ext}")

            res = process_single_file(
                input_file=file_path,
                output_file=curr_out,
                target_format=target_ext,
                crf=args.crf,
                preset=args.preset,
                audio_bitrate=args.audio_bitrate,
                copy_streams=args.copy,
                overwrite=args.yes,
                delete_original=args.delete_original,
            )
            results.append(res)

        # Tổng kết kết quả
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count

        if HAS_RICH:
            summary_table = Table(title="[bold green]Báo cáo hoàn thành[/bold green]")
            summary_table.add_column("File nguồn", style="yellow")
            summary_table.add_column("File đích", style="cyan")
            summary_table.add_column("Dung lượng đích", justify="right")
            summary_table.add_column("Thời gian", justify="right")
            summary_table.add_column("Trạng thái", justify="center")

            for r in results:
                status = "[green]Thành công[/green]" if r.success else "[red]Lỗi[/red]"
                summary_table.add_row(
                    r.input_path.name,
                    r.output_path.name if r.success else "--",
                    format_size(r.output_size_bytes) if r.success else "--",
                    f"{r.elapsed_time}s",
                    status,
                )
            console.print("\n", summary_table)
            console.print(f"\n[bold]Hoàn tất:[/bold] [green]{success_count} thành công[/green], [red]{failed_count} thất bại[/red].")
        else:
            print(f"\nHoàn tất: {success_count} thành công, {failed_count} thất bại.")

        sys.exit(0 if failed_count == 0 else 1)

    # Chế độ chuyển đổi 1 file
    input_file = Path(single_target).resolve()
    if not input_file.is_file():
        print_error(f"File nguồn không tồn tại: {input_file}")
        sys.exit(1)

    out_file = Path(args.output).resolve() if args.output else None
    if out_file and out_file.is_dir():
        target_ext = (args.to or get_default_target_ext(input_file)).lstrip(".").lower()
        out_file = out_file / input_file.with_suffix(f".{target_ext}").name

    res = process_single_file(
        input_file=input_file,
        output_file=out_file,
        target_format=args.to,
        crf=args.crf,
        preset=args.preset,
        audio_bitrate=args.audio_bitrate,
        copy_streams=args.copy,
        overwrite=args.yes,
        delete_original=args.delete_original,
    )

    sys.exit(0 if res.success else 1)


if __name__ == "__main__":
    main()
