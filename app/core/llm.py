from __future__ import annotations
import json
import os
import urllib.request
from typing import List, Dict, Any

DEEPSEEK_API_KEY_INLINE = "sk-877385db018840dbb6aa7cee1995fd68"

def deepseek_chat(messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
    api_key = (DEEPSEEK_API_KEY_INLINE or os.environ.get("DEEPSEEK_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY")
    base_url = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/")
    url = f"{base_url}/chat/completions"
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
        data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("DeepSeek 返回为空")
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    return content.strip()
