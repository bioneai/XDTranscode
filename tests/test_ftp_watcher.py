"""Test gestione errori FTP watcher."""

import unittest
from unittest.mock import MagicMock, patch

from ftputil.error import PermanentError


class TestFTPWatcherErrors(unittest.TestCase):
    @patch('ftp_watcher.ftputil.FTPHost')
    def test_login_error_sets_status_error(self, mock_ftp_host):
        mock_ftp_host.side_effect = PermanentError('530 Login incorrect.')

        from ftp_watcher import FTPWatcher

        watcher = FTPWatcher(6, MagicMock())
        watcher.running = True
        watcher._set_watchfolder_status = MagicMock()

        with self.assertRaises(PermanentError):
            watcher._check_ftp_files()

    def test_ftp_exceptions_tuple_includes_permanent_error(self):
        from ftp_utils import FTP_EXCEPTIONS

        self.assertIn(PermanentError, FTP_EXCEPTIONS)

    def test_ftputil_module_has_no_ftp_error_attribute(self):
        import ftputil

        self.assertFalse(hasattr(ftputil, 'FTPError'))


if __name__ == '__main__':
    unittest.main()
