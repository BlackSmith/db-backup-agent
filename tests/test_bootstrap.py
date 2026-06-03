"""Bootstrap smoke tests."""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from backup_agent.app.main import main


class BootstrapSmokeTests(unittest.TestCase):
    def test_main_returns_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "RSYNC_REMOTE_HOST": "nas.local",
                "RSYNC_REMOTE_USER": "backup",
                "RSYNC_REMOTE_PASSWORD": "secret",
                "BACKUP_TIME": "02:00",
                "BACKUP_RETENTION_DAYS": "7",
                "LOCAL_BACKUP_DIR": temp_dir,
                "TZ": "UTC",
            }
            with patch.dict("os.environ", env, clear=True):
                self.assertEqual(main(["--run-once"]), 0)


if __name__ == "__main__":
    unittest.main()
