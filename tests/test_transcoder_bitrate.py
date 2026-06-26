import unittest

from transcoder_worker import should_add_video_bitrate, is_libvvenc_available


class TestVideoBitrateHelper(unittest.TestCase):
    def test_prores_skips_bitrate(self):
        self.assertFalse(should_add_video_bitrate("prores_ks", "50000k"))
        self.assertFalse(should_add_video_bitrate("prores", "120M"))

    def test_empty_or_zero_skips_bitrate(self):
        self.assertFalse(should_add_video_bitrate("libx264", ""))
        self.assertFalse(should_add_video_bitrate("libx264", "0"))

    def test_normal_codec_uses_bitrate(self):
        self.assertTrue(should_add_video_bitrate("libx264", "15000k"))
        self.assertTrue(should_add_video_bitrate("dnxhd", "120M"))

    def test_libvvenc_check_returns_bool(self):
        self.assertIsInstance(is_libvvenc_available(), bool)


if __name__ == "__main__":
    unittest.main()
