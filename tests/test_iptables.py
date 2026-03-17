from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from doubleagent.iptables import add_pid_to_cgroup
from doubleagent.iptables import build_proxy_cgroup_path
from doubleagent.iptables import ensure_cgroup
from doubleagent.iptables import get_process_cgroup_path
from doubleagent.iptables import remove_cgroup


class IptablesTests(unittest.TestCase):
    def test_get_process_cgroup_path_reads_cgroup_v2_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doubleagent-cgroup-") as tmpdir:
            path = Path(tmpdir) / "cgroup"
            path.write_text("0::/docker/abc123\n", encoding="utf-8")
            self.assertEqual(get_process_cgroup_path(path), "/docker/abc123")

    def test_get_process_cgroup_path_accepts_root_cgroup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doubleagent-cgroup-") as tmpdir:
            path = Path(tmpdir) / "cgroup"
            path.write_text("0::/\n", encoding="utf-8")
            self.assertEqual(get_process_cgroup_path(path), "/")

    def test_build_proxy_cgroup_path_under_root(self) -> None:
        self.assertEqual(build_proxy_cgroup_path("/"), "/doubleagent-proxy")

    def test_build_proxy_cgroup_path_under_nested_cgroup(self) -> None:
        self.assertEqual(
            build_proxy_cgroup_path("/docker/abc123"),
            "/docker/abc123/doubleagent-proxy",
        )

    def test_manage_proxy_child_cgroup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="doubleagent-cgroupfs-") as tmpdir:
            cgroup_root = Path(tmpdir)
            cgroup_path = "/doubleagent-proxy"
            cgroup_dir = ensure_cgroup(cgroup_path, cgroup_root)
            self.assertTrue(cgroup_dir.is_dir())
            add_pid_to_cgroup(1234, cgroup_path, cgroup_root)
            self.assertEqual((cgroup_dir / "cgroup.procs").read_text(encoding="utf-8"), "1234\n")
            (cgroup_dir / "cgroup.procs").unlink()
            remove_cgroup(cgroup_path, cgroup_root)
            self.assertFalse(cgroup_dir.exists())


if __name__ == "__main__":
    unittest.main()
