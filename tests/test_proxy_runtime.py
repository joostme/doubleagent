from __future__ import annotations

import unittest

from doubleagent.main import build_mitmdump_command


class ProxyRuntimeTests(unittest.TestCase):
    def test_build_mitmdump_command_uses_regular_mode(self) -> None:
        command = build_mitmdump_command(8080, "/tmp/confdir")

        self.assertIn("regular", command)
        self.assertNotIn("transparent", command)
        self.assertEqual(command[0], "mitmdump")


if __name__ == "__main__":
    unittest.main()
