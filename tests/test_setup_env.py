import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import setup_env  # noqa: E402


class EnvFileTests(unittest.TestCase):
    def test_parse_ignores_comments_and_strips_quotes(self):
        text = '# comment\n\nA=1\nB="two"\nC=\'three\'\nD=\nnot a line\n'
        self.assertEqual(setup_env.parse_env(text), {"A": "1", "B": "two", "C": "three", "D": ""})

    def test_write_then_read_roundtrip_with_600_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            values = {"TELEGRAM_BOT_TOKEN": "123:abc", "SUPABASE_URL": "https://x.supabase.co", "EXTRA": "1"}
            setup_env.write_env(values, path)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            read_back = setup_env.read_env(path)
            for key, value in values.items():
                self.assertEqual(read_back[key], value)
            # every known key is written, even if empty
            for key in setup_env.ENV_KEYS:
                self.assertIn(key, read_back)

    def test_read_missing_file_returns_empty(self):
        self.assertEqual(setup_env.read_env("/nonexistent/.env"), {})


class ValidationTests(unittest.TestCase):
    def test_valid_values(self):
        cases = {
            "TELEGRAM_BOT_TOKEN": "1234567890:" + "FAKE_TEST_TOKEN_" + "x" * 20,
            "TELEGRAM_CHAT_ID": "123456789",
            "SUPABASE_URL": "https://abcdefgh.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_abc123",
            "SUPABASE_SECRET_KEY": "sb_secret_abc123",
            "ANTHROPIC_API_KEY": "sk-ant-api03-" + "x" * 30,
        }
        for key, value in cases.items():
            self.assertTrue(setup_env.is_valid(key, value), key)

    def test_invalid_values(self):
        cases = {
            "TELEGRAM_BOT_TOKEN": "not-a-token",
            "SUPABASE_URL": "http://abcdefgh.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_secret_abc",
            "SUPABASE_SECRET_KEY": "sb_publishable_abc",
            "ANTHROPIC_API_KEY": "sk-proj-123",
        }
        for key, value in cases.items():
            self.assertFalse(setup_env.is_valid(key, value), key)

    def test_empty_is_invalid(self):
        self.assertFalse(setup_env.is_valid("ANTHROPIC_API_KEY", ""))

    def test_normalize_strips_whitespace_and_trailing_slash(self):
        self.assertEqual(setup_env.normalize("SUPABASE_URL", " https://a.supabase.co/ "), "https://a.supabase.co")
        self.assertEqual(setup_env.normalize("ANTHROPIC_API_KEY", " sk-ant-x \n"), "sk-ant-x")


class TelegramParsingTests(unittest.TestCase):
    UPDATES = [
        {"update_id": 10, "message": {"chat": {"id": -100555, "type": "group"}}},
        {"update_id": 11, "message": {"chat": {"id": 42, "type": "private", "first_name": "Test"}}},
        {"update_id": 12, "my_chat_member": {"chat": {"id": 99, "type": "private"}}},
    ]

    def test_extracts_latest_private_chat(self):
        self.assertEqual(setup_env.extract_private_chat(self.UPDATES), (42, "Test"))

    def test_no_private_chat(self):
        self.assertEqual(setup_env.extract_private_chat(self.UPDATES[:1]), (None, None))
        self.assertEqual(setup_env.extract_private_chat([]), (None, None))

    def test_latest_update_id(self):
        self.assertEqual(setup_env.latest_update_id(self.UPDATES), 12)
        self.assertIsNone(setup_env.latest_update_id([]))


if __name__ == "__main__":
    unittest.main()
