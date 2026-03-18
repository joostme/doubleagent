from __future__ import annotations

import unittest

from doubleagent.main import build_mitmdump_command


class ProxyRuntimeTests(unittest.TestCase):
    def test_build_mitmdump_command_uses_regular_mode(self) -> None:
        command = build_mitmdump_command(8080, "/tmp/confdir", "info")

        self.assertIn("regular", command)
        self.assertNotIn("transparent", command)
        self.assertEqual(command[0], "mitmdump")
        self.assertIn("termlog_verbosity=warn", command)
        self.assertIn("flow_detail=0", command)

    def test_build_mitmdump_command_enables_verbose_output_for_debug(self) -> None:
        command = build_mitmdump_command(8080, "/tmp/confdir", "debug")

        self.assertIn("termlog_verbosity=debug", command)
        self.assertIn("flow_detail=1", command)


if __name__ == "__main__":
    unittest.main()
