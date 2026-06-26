import os
import sys
import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Base, WatchFolder, TranscodeJob, FileStatus, TranscodePreset
from transcoder_worker import pick_next_pending_job, FALLBACK_JOB_PRIORITY


class TestWatchfolderPriority(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

        preset = TranscodePreset(name="TEST", container="mxf")
        self.session.add(preset)
        self.session.commit()

        self.preset_id = preset.id

    def tearDown(self):
        self.session.close()

    def _add_watchfolder(self, name, priority):
        wf = WatchFolder(
            name=name,
            path=f"/in/{name}",
            output_path=f"/out/{name}",
            active=1,
            priority=priority,
            preset_id=self.preset_id,
        )
        self.session.add(wf)
        self.session.commit()
        return wf

    def _add_job(self, watchfolder_id, filename, created_at=None):
        job = TranscodeJob(
            watchfolder_id=watchfolder_id,
            preset_id=self.preset_id,
            input_filename=filename,
            input_path=f"/in/{filename}",
            output_path=f"/out/{filename}.mxf",
            status=FileStatus.PENDING,
            created_at=created_at or datetime.utcnow(),
        )
        self.session.add(job)
        self.session.commit()
        return job

    def test_lower_priority_number_picked_first(self):
        wf_high = self._add_watchfolder("HIGH", 1)
        wf_low = self._add_watchfolder("LOW", 5)
        self._add_job(wf_low.id, "low_first.mov", datetime.utcnow() - timedelta(minutes=10))
        self._add_job(wf_high.id, "high_later.mov", datetime.utcnow())

        job = pick_next_pending_job(self.session)
        self.assertIsNotNone(job)
        self.assertEqual(job.input_filename, "high_later.mov")

    def test_fifo_within_same_priority(self):
        wf = self._add_watchfolder("SAME", 10)
        self._add_job(wf.id, "second.mov", datetime.utcnow())
        self._add_job(wf.id, "first.mov", datetime.utcnow() - timedelta(minutes=5))

        job = pick_next_pending_job(self.session)
        self.assertEqual(job.input_filename, "first.mov")

    def test_job_without_watchfolder_last(self):
        wf = self._add_watchfolder("WF", 10)
        orphan = TranscodeJob(
            watchfolder_id=None,
            preset_id=self.preset_id,
            input_filename="orphan.mov",
            input_path="/in/orphan.mov",
            output_path="/out/orphan.mxf",
            status=FileStatus.PENDING,
            created_at=datetime.utcnow() - timedelta(hours=1),
        )
        self.session.add(orphan)
        self.session.commit()
        self._add_job(wf.id, "wf_job.mov", datetime.utcnow())

        job = pick_next_pending_job(self.session)
        self.assertEqual(job.input_filename, "wf_job.mov")

    def test_only_pending_unassigned_jobs(self):
        wf = self._add_watchfolder("WF", 1)
        processing = self._add_job(wf.id, "busy.mov")
        processing.status = FileStatus.PROCESSING
        processing.worker_id = 1
        pending = self._add_job(wf.id, "waiting.mov")
        self.session.commit()

        job = pick_next_pending_job(self.session)
        self.assertEqual(job.id, pending.id)

    def test_fallback_priority_constant(self):
        self.assertEqual(FALLBACK_JOB_PRIORITY, 999)


if __name__ == "__main__":
    unittest.main()
