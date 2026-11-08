import os
import re
from typing import List
import requests

def split_markdown_message(text: str, max_length: int = 4000) -> List[str]:
    """Split text into chunks below Telegram's 4096-character limit preserving line breaks."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    lines = text.split("\n")
    current_chunk = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1  # include newline
        if current_len + line_len > max_length:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            
            # If a single line is excessively long
            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]
                
        current_chunk.append(line)
        current_len += len(line) + 1

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks

def send_telegram_digest(digest_markdown: str) -> bool:
    """
    Send digest to Telegram using bot token and chat ID from environment variables.
    Returns True if sent successfully, False otherwise.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = split_markdown_message(digest_markdown)

    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            # If markdown parsing fails due to unmatched asterisks, fallback to plain text
            if resp.status_code == 400 and "can't parse entities" in resp.text:
                payload.pop("parse_mode", None)
                resp = requests.post(url, json=payload, timeout=15)

            if resp.status_code != 200:
                print(f"[WARN] Telegram delivery failed for chunk {i+1}: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            print(f"[WARN] Error sending Telegram message: {e}")
            return False

    return True
