import traceback
import unittest
from unittest import mock

import requests

import notify

TOKEN = "123456:SECRET-token"


def response(status, body):
    r = mock.Mock(status_code=status)
    r.json.return_value = body
    return r


class SendTest(unittest.TestCase):
    def test_posts_message(self):
        with mock.patch("requests.post", return_value=response(200, {"ok": True})) as post:
            notify.send("hello", TOKEN, "42")
        post.assert_called_once_with("https://api.telegram.org/bot123456:SECRET-token/sendMessage",
                                     json={"chat_id": "42", "text": "hello"}, timeout=30)

    def test_not_ok_raises(self):
        body = {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}
        with mock.patch("requests.post", return_value=response(400, body)), \
                self.assertRaises(RuntimeError) as cm:
            notify.send("hello", TOKEN, "42")
        self.assertEqual(str(cm.exception), "Telegram 400: Bad Request: chat not found")

    def test_connection_error_hides_token(self):
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        error = requests.ConnectionError(f"Max retries exceeded with url: {url}")
        with mock.patch("requests.post", side_effect=error), self.assertRaises(RuntimeError) as cm:
            notify.send("hello", TOKEN, "42")
        self.assertEqual(str(cm.exception), "Telegram send failed: ConnectionError("
                         "'Max retries exceeded with url: https://api.telegram.org/bot***/sendMessage')")
        self.assertNotIn("SECRET", "".join(traceback.format_exception(cm.exception)))


if __name__ == "__main__":
    unittest.main()
