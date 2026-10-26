import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec("mcp"), "optional QQ MCP dependencies are not installed")
class QQReadOnlyTests(unittest.TestCase):
    def test_settings_are_local_and_actions_are_read_only(self):
        from integrations.qq_readonly import server

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            original = server.SETTINGS
            try:
                server.SETTINGS = path
                path.write_text(json.dumps({
                    "api_url": "http://127.0.0.1:3033",
                    "api_token": "test-only-random-token",
                    "allowed_chats": ["group:123456789"],
                }), encoding="utf-8")
                self.assertEqual(server.settings()["allowed_chats"], ["group:123456789"])
                self.assertFalse(any("send" in action or "delete" in action for action in server.READ_ACTIONS))

                path.write_text(json.dumps({
                    "api_url": "http://example.com:3033",
                    "api_token": "test-only-random-token",
                    "allowed_chats": [],
                }), encoding="utf-8")
                with self.assertRaises(ValueError):
                    server.settings()
            finally:
                server.SETTINGS = original


if __name__ == "__main__":
    unittest.main()
