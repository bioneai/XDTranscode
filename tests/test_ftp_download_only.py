"""Test modalità FTP solo download."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from models import FileStatus, OPERATION_MODE_DOWNLOAD_ONLY, OPERATION_MODE_TRANSCODE
from ftp_utils import is_download_only_watchfolder, job_blocks_ftp_redetection


class TestFTPDownloadOnly(unittest.TestCase):
    def _watchfolder(self, **kwargs):
        wf = MagicMock()
        wf.watch_type = kwargs.get('watch_type', 'ftp')
        wf.operation_mode = kwargs.get('operation_mode', OPERATION_MODE_TRANSCODE)
        return wf

    def test_is_download_only_for_ftp_mode(self):
        wf = self._watchfolder(operation_mode=OPERATION_MODE_DOWNLOAD_ONLY)
        self.assertTrue(is_download_only_watchfolder(wf))

    def test_is_download_only_false_for_transcode(self):
        wf = self._watchfolder(operation_mode=OPERATION_MODE_TRANSCODE)
        self.assertFalse(is_download_only_watchfolder(wf))

    def test_is_download_only_false_for_local(self):
        wf = self._watchfolder(watch_type='local', operation_mode=OPERATION_MODE_DOWNLOAD_ONLY)
        self.assertFalse(is_download_only_watchfolder(wf))

    def test_failed_job_without_file_allows_redetection(self):
        job = MagicMock()
        job.status = FileStatus.FAILED
        job.input_path = '/tmp/missing_file.m4v'
        self.assertFalse(job_blocks_ftp_redetection(job))

    def test_completed_job_blocks_redetection(self):
        job = MagicMock()
        job.status = FileStatus.COMPLETED
        job.input_path = '/tmp/exists.m4v'
        self.assertTrue(job_blocks_ftp_redetection(job))

    def test_failed_job_with_existing_file_blocks_redetection(self):
        with tempfile.NamedTemporaryFile(suffix='.m4v', delete=False) as tmp:
            path = tmp.name
        try:
            job = MagicMock()
            job.status = FileStatus.FAILED
            job.input_path = path
            self.assertTrue(job_blocks_ftp_redetection(job))
        finally:
            os.remove(path)


if __name__ == '__main__':
    unittest.main()
