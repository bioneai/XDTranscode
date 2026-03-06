import unittest

from transcoder_worker import TranscoderWorker


class TestFFprobeParsing(unittest.TestCase):
    def setUp(self):
        # db_session_factory non usata nei test parsing
        self.worker = TranscoderWorker(lambda: None)

    def test_timecode_from_format_tags(self):
        data = {"format": {"tags": {"timecode": "10:00:00:00"}}}
        self.assertEqual(self.worker._extract_timecode_from_ffprobe(data), "10:00:00:00")

    def test_timecode_from_stream_tags(self):
        data = {"streams": [{"codec_type": "video", "tags": {"timecode": "01:02:03:04"}}]}
        self.assertEqual(self.worker._extract_timecode_from_ffprobe(data), "01:02:03:04")

    def test_timecode_from_tmcd_stream(self):
        data = {"streams": [{"codec_name": "tmcd", "tags": {"timecode": "00:00:00:00"}}]}
        self.assertEqual(self.worker._extract_timecode_from_ffprobe(data), "00:00:00:00")

    def test_parse_rate_integer(self):
        self.assertAlmostEqual(self.worker._parse_ffprobe_rate("25/1"), 25.0)

    def test_parse_rate_ntsc(self):
        self.assertAlmostEqual(self.worker._parse_ffprobe_rate("30000/1001"), 29.97002997, places=5)

    def test_build_drawtext_quotes_timecode_and_escapes_colons(self):
        # patch: evita ffprobe e forza valori noti
        self.worker._get_source_timecode_and_fps = lambda _p: ("15:51:00:21", 25.0)
        drawtext = self.worker._build_timecode_drawtext("/dev/null")
        self.assertIn("drawtext=", drawtext)
        self.assertIn("timecode='15\\:51\\:00\\:21'", drawtext)
        self.assertIn(":r=25", drawtext)

    def test_build_command_injects_timecode_and_watermark_for_tc_wtmk(self):
        # patch: evita ffprobe e forza valori noti
        self.worker._get_source_timecode_and_fps = lambda _p: ("15:51:00:21", 25.0)

        class P:
            name = "H264_LOWRES_TC_WTMK"
            video_codec = "libx264"
            video_bitrate = "800k"
            audio_codec = "aac"
            audio_bitrate = "128k"
            audio_sample_rate = "48000"
            audio_channels = "2"
            ffmpeg_params = "-vf yadif,scale=1024:576 -profile:v high -level 4.2 -pix_fmt yuv420p -af loudnorm -movflags +faststart"

        class J:
            input_path = "/mnt/raid0/TRANSCODE_V3/AUTO_IN/IN_CopiaVisione/D008C001_250110JTS06.MP4"
            output_path = "/tmp/_dryrun_tc_wtmk.mp4"
            preset = P()

        cmd = self.worker._build_ffmpeg_command(J())
        self.assertIn("-vf", cmd)
        vf = cmd[cmd.index("-vf") + 1]
        self.assertIn("timecode='15\\:51\\:00\\:21'", vf)
        self.assertIn(":r=25", vf)
        self.assertIn("text='COPIA VISIONE'", vf)
        self.assertGreaterEqual(vf.count("drawtext="), 2)


if __name__ == "__main__":
    unittest.main()

