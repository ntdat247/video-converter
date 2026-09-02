"""
test_converter.py - Bộ kiểm thử tự động cho converter WebM sang MP4
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from converter import (
    ConversionProgress,
    check_dependencies,
    convert_file,
    get_media_info,
)


class TestWebMConverter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.has_ffmpeg = shutil.which("ffmpeg") is not None
        cls.test_dir = Path(tempfile.mkdtemp(prefix="webm2mp4_test_"))

        # Tạo file webm test có âm thanh
        cls.sample_with_audio = cls.test_dir / "test_audio.webm"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=800:duration=2",
                "-c:v", "libvpx-vp9", "-c:a", "libopus",
                str(cls.sample_with_audio),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

        # Tạo file webm test không có âm thanh (silent)
        cls.sample_silent = cls.test_dir / "test_silent.webm"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=20",
                "-c:v", "libvpx-vp9",
                str(cls.sample_silent),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir)

    def test_check_dependencies(self):
        ready, msg = check_dependencies()
        self.assertTrue(ready, f"FFmpeg dependencies check failed: {msg}")

    def test_get_media_info(self):
        info = get_media_info(self.sample_with_audio)
        self.assertAlmostEqual(info.duration, 2.0, delta=0.2)
        self.assertEqual(info.width, 320)
        self.assertEqual(info.height, 240)
        self.assertIn(info.video_codec, ["vp9", "libvpx-vp9"])
        self.assertEqual(info.audio_codec, "opus")

    def test_convert_video_with_audio(self):
        output_mp4 = self.test_dir / "test_audio.mp4"
        progress_records = []

        def on_progress(p: ConversionProgress):
            progress_records.append(p.percentage)

        res = convert_file(
            input_path=self.sample_with_audio,
            output_path=output_mp4,
            crf=23,
            preset="ultrafast",
            progress_callback=on_progress,
        )

        self.assertTrue(res.success, f"Convert failed: {res.error_message}")
        self.assertTrue(output_mp4.exists())
        self.assertGreater(output_mp4.stat().st_size, 0)
        self.assertGreater(len(progress_records), 0)
        self.assertEqual(progress_records[-1], 100.0)

        # Verify output media info
        info = get_media_info(output_mp4)
        self.assertEqual(info.video_codec, "h264")
        self.assertEqual(info.audio_codec, "aac")
        self.assertAlmostEqual(info.duration, 2.0, delta=0.2)

    def test_convert_silent_video(self):
        output_mp4 = self.test_dir / "test_silent.mp4"
        res = convert_file(
            input_path=self.sample_silent,
            output_path=output_mp4,
            crf=24,
            preset="ultrafast",
        )

        self.assertTrue(res.success, f"Convert silent failed: {res.error_message}")
        self.assertTrue(output_mp4.exists())

        info = get_media_info(output_mp4)
        self.assertEqual(info.video_codec, "h264")
        self.assertIsNone(info.audio_codec)

    def test_nonexistent_file(self):
        fake_path = self.test_dir / "non_existent.webm"
        res = convert_file(fake_path)
        self.assertFalse(res.success)
        self.assertIn("không tồn tại", res.error_message)

    def test_extract_webm_duration(self):
        from converter import extract_webm_duration
        dur = extract_webm_duration(self.sample_with_audio)
        self.assertAlmostEqual(dur, 2.0, delta=0.3)

    def test_convert_mp4_to_webm(self):
        # Tạo file mp4 trước
        mp4_path = self.test_dir / "base.mp4"
        convert_file(self.sample_with_audio, mp4_path, preset="ultrafast")
        self.assertTrue(mp4_path.exists())

        # mp4 -> webm
        webm_out = self.test_dir / "converted_from_mp4.webm"
        res = convert_file(mp4_path, webm_out, preset="ultrafast")
        self.assertTrue(res.success, f"mp4 -> webm failed: {res.error_message}")
        self.assertTrue(webm_out.exists())

        info = get_media_info(webm_out)
        self.assertIn(info.video_codec, ["vp9", "libvpx-vp9"])
        self.assertEqual(info.audio_codec, "opus")

    def test_convert_mp4_to_mov_and_back(self):
        # mp4 -> mov
        mp4_path = self.test_dir / "base.mp4"
        if not mp4_path.exists():
            convert_file(self.sample_with_audio, mp4_path, preset="ultrafast")

        mov_out = self.test_dir / "converted_from_mp4.mov"
        res = convert_file(mp4_path, mov_out, preset="ultrafast")
        self.assertTrue(res.success, f"mp4 -> mov failed: {res.error_message}")
        self.assertTrue(mov_out.exists())

        info_mov = get_media_info(mov_out)
        self.assertEqual(info_mov.video_codec, "h264")
        self.assertEqual(info_mov.audio_codec, "aac")

        # mov -> mp4
        mp4_from_mov = self.test_dir / "converted_from_mov.mp4"
        res2 = convert_file(mov_out, mp4_from_mov, preset="ultrafast")
        self.assertTrue(res2.success, f"mov -> mp4 failed: {res2.error_message}")
        self.assertTrue(mp4_from_mov.exists())

    def test_convert_copy_streams(self):
        # mp4 -> mov with copy_streams=True
        mp4_path = self.test_dir / "base.mp4"
        if not mp4_path.exists():
            convert_file(self.sample_with_audio, mp4_path, preset="ultrafast")

        mov_copy = self.test_dir / "remux_copy.mov"
        res = convert_file(mp4_path, mov_copy, copy_streams=True)
        self.assertTrue(res.success, f"copy streams failed: {res.error_message}")
        self.assertTrue(mov_copy.exists())
        self.assertLess(res.elapsed_time, 2.0)  # Remux must be practically instant!


if __name__ == "__main__":
    unittest.main()
