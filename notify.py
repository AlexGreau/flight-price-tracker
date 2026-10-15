"""Telegram sendMessage over plain HTTP."""
import requests


def send(text, token, chat_id):
    """Raises RuntimeError on any failure; the message never contains the bot token."""
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": text}, timeout=30)
        body = r.json()
    except (requests.RequestException, ValueError) as e:
        # requests exceptions embed the URL, which carries the token; `from None` keeps it out of tracebacks.
        raise RuntimeError(f"Telegram send failed: {e!r}".replace(token, "***")) from None
    if r.status_code != 200 or not body.get("ok"):
        raise RuntimeError(f"Telegram {r.status_code}: {body.get('description')}".replace(token, "***"))
