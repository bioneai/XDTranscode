import os
import sys
import tempfile
import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Base, TranscodeJob, FileStatus, TranscodePreset, WatchFolder
from job_actions import pause_job, cancel_job, requeue_job


class TestJobActions(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

        preset = TranscodePreset(name="TEST", container="mp4", video_codec="libx264", video_bitrate="1M")
        self.session.add(preset)
        self.session.commit()
        self.preset_id = preset.id

        self.tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self.tmp.write(b"test")
        self.tmp.close()
        self.input_path = self.tmp.name

    def tearDown(self):
        self.session.close()
        if os.path.exists(self.input_path):
            os.remove(self.input_path)

    def _job(self, status=FileStatus.PENDING):
        job = TranscodeJob(
            watchfolder_id=None,
            preset_id=self.preset_id,
            input_filename="test.mp4",
            input_path=self.input_path,
            output_path=self.input_path + ".out.mp4",
            status=status,
            progress=10,
            worker_id=1,
            error_message="err",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        self.session.add(job)
        self.session.commit()
        return job

    def test_pause_pending(self):
        job = self._job(FileStatus.PENDING)
        pause_job(job)
        self.assertEqual(job.status, FileStatus.PAUSED)
        self.assertIsNone(job.worker_id)

    def test_pause_processing(self):
        job = self._job(FileStatus.PROCESSING)
        pause_job(job)
        self.assertEqual(job.status, FileStatus.PAUSED)

    def test_cancel_paused(self):
        job = self._job(FileStatus.PAUSED)
        cancel_job(job)
        self.assertEqual(job.status, FileStatus.CANCELLED)

    def test_requeue_failed(self):
        job = self._job(FileStatus.FAILED)
        requeue_job(job)
        self.assertEqual(job.status, FileStatus.PENDING)
        self.assertEqual(job.progress, 0)
        self.assertIsNone(job.error_message)
        self.assertIsNone(job.worker_id)

    def test_requeue_missing_input_raises(self):
        job = self._job(FileStatus.CANCELLED)
        os.remove(self.input_path)
        self.input_path = ""
        with self.assertRaises(ValueError):
            requeue_job(job)

    def test_resume_paused(self):
        from job_actions import resume_job
        job = self._job(FileStatus.PAUSED)
        resume_job(job)
        self.assertEqual(job.status, FileStatus.PENDING)

    def test_resume_non_paused_raises(self):
        from job_actions import resume_job
        job = self._job(FileStatus.FAILED)
        with self.assertRaises(ValueError):
            resume_job(job)

    def test_pause_completed_raises(self):
        job = self._job(FileStatus.COMPLETED)
        with self.assertRaises(ValueError):
            pause_job(job)


if __name__ == "__main__":
    unittest.main()
