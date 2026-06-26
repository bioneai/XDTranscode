import os
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Base, TranscodePreset
from scripts.seed_presets import BROADCAST_PRESETS, seed_broadcast_presets


class TestSeedPresets(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def tearDown(self):
        self.session.close()

    def test_seed_creates_all_presets_without_encoder_gate(self):
        all_encoders = {"dnxhd", "libx264", "libx265", "libvvenc", "prores_ks"}
        stats = seed_broadcast_presets(self.session, all_encoders, verbose=False)
        self.assertEqual(len(stats["created"]), len(BROADCAST_PRESETS))
        names = {p.name for p in self.session.query(TranscodePreset).all()}
        for spec in BROADCAST_PRESETS:
            self.assertIn(spec["name"], names)

    def test_seed_is_idempotent(self):
        encoders = {"dnxhd", "libx264", "libx265", "libvvenc", "prores_ks"}
        seed_broadcast_presets(self.session, encoders, verbose=False)
        stats = seed_broadcast_presets(self.session, encoders, verbose=False)
        self.assertEqual(stats["created"], [])
        self.assertEqual(len(stats["skipped"]), len(BROADCAST_PRESETS))

    def test_h266_skipped_without_libvvenc(self):
        encoders = {"dnxhd", "libx264", "libx265", "prores_ks"}
        stats = seed_broadcast_presets(self.session, encoders, verbose=False)
        self.assertIn("H266_HQ", stats["skipped_encoder"])
        names = {p.name for p in self.session.query(TranscodePreset).all()}
        self.assertNotIn("H266_HQ", names)
        self.assertIn("H264_HQ", names)

    def test_prores_has_zero_bitrate(self):
        encoders = {"prores_ks"}
        seed_broadcast_presets(self.session, encoders, verbose=False)
        preset = self.session.query(TranscodePreset).filter(TranscodePreset.name == "PRORES_HQ").first()
        self.assertIsNotNone(preset)
        self.assertEqual(preset.video_bitrate, "0")
        self.assertEqual(preset.video_codec, "prores_ks")


if __name__ == "__main__":
    unittest.main()
