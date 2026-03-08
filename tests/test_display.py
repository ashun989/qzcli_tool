from datetime import datetime, timedelta
import unittest

from qzcli.display import (
    format_duration,
    format_time_ago,
    get_status_display,
    truncate_string,
)


class DisplayHelperTests(unittest.TestCase):
    def test_get_status_display_returns_default_for_unknown_status(self):
        style, icon, name = get_status_display("custom_status")

        self.assertEqual(style, "dim")
        self.assertEqual(icon, "?")
        self.assertEqual(name, "custom_status")

    def test_format_duration_covers_seconds_minutes_and_hours(self):
        self.assertEqual(format_duration("15000"), "15秒")
        self.assertEqual(format_duration("65000"), "1分5秒")
        self.assertEqual(format_duration("3661000"), "1小时1分")
        self.assertEqual(format_duration("bad"), "-")

    def test_format_time_ago_handles_recent_and_invalid_values(self):
        just_now = (datetime.now() - timedelta(seconds=10)).isoformat()
        minutes_ago = (datetime.now() - timedelta(minutes=5)).isoformat()

        self.assertEqual(format_time_ago(""), "-")
        self.assertEqual(format_time_ago("bad-time"), "-")
        self.assertTrue(format_time_ago(just_now).endswith("秒前"))
        self.assertEqual(format_time_ago(minutes_ago), "5分钟前")

    def test_truncate_string_preserves_short_values(self):
        self.assertEqual(truncate_string("abc", 5), "abc")
        self.assertEqual(truncate_string("abcdef", 5), "ab...")


if __name__ == "__main__":
    unittest.main()
