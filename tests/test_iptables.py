from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from doubleagent.iptables import get_process_cgroup_path


class IptablesTests(unittest.TestCase):
    def test_get_process_cgroup_path_reads_cgroup_v2_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doubleagent-cgroup-") as tmpdir:
            path = Path(tmpdir) / "cgroup"
            path.write_text("0::/docker/abc123\n", encoding="utf-8")
            self.assertEqual(get_process_cgroup_path(path), "/docker/abc123")

    def test_get_process_cgroup_path_rejects_root_cgroup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doubleagent-cgroup-") as tmpdir:
            path = Path(tmpdir) / "cgroup"
            path.write_text("0::/\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                get_process_cgroup_path(path)


if __name__ == "__main__":
    unittest.main()
