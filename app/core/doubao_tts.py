from __future__ import annotations
import base64
import json
import os
import uuid
import urllib.error
import urllib.request
from typing import Tuple, Any, Dict, Optional

DOUBAO_APP_ID_INLINE = "5563606518"
DOUBAO_ACCESS_TOKEN_INLINE = "1mX4YADB8E5TWHiSSPvd5vkAW4INGzRV"
DOUBAO_RESOURCE_ID_INLINE = ""
DOUBAO_CLUSTER_INLINE = ""
DOUBAO_API_URL_V3 = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
DOUBAO_API_URL_V1 = "https://openspeech.bytedance.com/api/v1/tts"
DOUBAO_VOICE_TYPE_INLINE = "zh_female_vv_uranus_bigtts"

def _get_value(env_key: str, inline_value: str) -> str:
    return (os.environ.get(env_key, "") or inline_value or "").strip()

def _request_json(url: str, body: bytes, headers: Dict[str, str]) -> Tuple[bytes, str, int]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read(), resp.headers.get("Content-Type", ""), resp.status
    except urllib.error.HTTPError as e:
        return e.read(), e.headers.get("Content-Type", ""), e.code

def _extract_audio(data: Any) -> Optional[str]:
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return None
    audio = data.get("audio")
    if isinstance(audio, str):
        return audio
    audio_base64 = data.get("audio_base64")
    if isinstance(audio_base64, str):
        return audio_base64
    inner = data.get("data")
    if isinstance(inner, str):
        return inner
    if isinstance(inner, dict):
        found = _extract_audio(inner)
        if found:
            return found
    if isinstance(inner, list):
        for item in inner:
            if isinstance(item, dict):
                found = _extract_audio(item)
                if found:
                    return found
    speech = data.get("speech")
    if isinstance(speech, dict):
        found = _extract_audio(speech)
        if found:
            return found
    result = data.get("result")
    if isinstance(result, dict):
        found = _extract_audio(result)
        if found:
            return found
    audio_url = data.get("audio_url")
    if isinstance(audio_url, str):
        return audio_url
    return None

def _try_parse_json(raw: bytes) -> Optional[Dict[str, Any]]:
    head = raw.lstrip()[:1]
    if head not in (b"{", b"["):
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None

def _parse_response(raw: bytes, content_type: str) -> Optional[Dict[str, Any]]:
    if "application/json" in content_type:
        return json.loads(raw.decode("utf-8"))
    return _try_parse_json(raw)

def _prefer_v1(resource_id: str, voice_type: str) -> bool:
    if resource_id:
        return False
    return True

def synthesize(text: str, voice_type: Optional[str] = None) -> Tuple[bytes, str]:
    appid = _get_value("DOUBAO_APP_ID", DOUBAO_APP_ID_INLINE)
    token = _get_value("DOUBAO_ACCESS_TOKEN", DOUBAO_ACCESS_TOKEN_INLINE)
    resource_id = _get_value("DOUBAO_RESOURCE_ID", DOUBAO_RESOURCE_ID_INLINE)
    cluster = _get_value("DOUBAO_CLUSTER", DOUBAO_CLUSTER_INLINE)
    voice_map = {
        "调皮公主": "saturn_zh_female_tiaopigongzhu_tob",
        "调皮公主 ": "saturn_zh_female_tiaopigongzhu_tob",
        "tiaopigongzhu": "saturn_zh_female_tiaopigongzhu_tob",
        "tiaopigongzhu_tob": "saturn_zh_female_tiaopigongzhu_tob",
        "可爱公主": "saturn_zh_female_keainvsheng_tob",
        "可爱公主 ": "saturn_zh_female_keainvsheng_tob",
        "keainvsheng": "saturn_zh_female_keainvsheng_tob",
        "keainvsheng_tob": "saturn_zh_female_keainvsheng_tob",
        "vivi": "zh_female_vv_uranus_bigtts",
        "vivi2.0": "zh_female_vv_uranus_bigtts",
        "vivi 2.0": "zh_female_vv_uranus_bigtts",
        "vv": "zh_female_vv_uranus_bigtts",
    }
    raw_voice = (voice_type or _get_value("DOUBAO_VOICE_TYPE", DOUBAO_VOICE_TYPE_INLINE) or "zh_female_vv_uranus_bigtts").strip()
    voice_type = voice_map.get(raw_voice, raw_voice)
    if not resource_id:
        if voice_type.startswith("saturn_"):
            resource_id = "seed-tts-2.0"
        elif "uranus" in voice_type or voice_type.endswith("bigtts"):
            resource_id = "seed-tts-1.0"
    base_voice_type = voice_type
    if not appid or not token:
        raise RuntimeError("缺少豆包TTS的APPID或Access Token")
    reqid = uuid.uuid4().hex
    def _make_audio_payload(v: str) -> Dict[str, Any]:
        speed = 1.0
        volume = 1.0
        pitch = 1.0
        if not v.startswith("saturn_"):
            speed = 0.95
            volume = 1.1
            pitch = 1.05
        return {
            "voice_type": v,
            "encoding": "mp3",
            "rate": 24000,
            "sample_rate": 24000,
            "speed_ratio": speed,
            "volume_ratio": volume,
            "pitch_ratio": pitch,
        }
    request_payload = {"reqid": reqid, "text": text, "text_type": "plain", "operation": "query"}
    def _call_v3() -> Tuple[bytes, str, int]:
        payload = {
            "app": {"appid": appid},
            "user": {"uid": "macos-desktop-agent"},
            "audio": _make_audio_payload(base_voice_type),
            "request": request_payload,
        }
        if base_voice_type.startswith("saturn_"):
            payload["request"]["model"] = _get_value("DOUBAO_TTS_MODEL", "seed-tts-2.0-expressive")
        if cluster:
            payload["app"]["cluster"] = cluster
        headers = {
            "Content-Type": "application/json",
            "X-Api-App-Id": appid,
            "X-Api-Access-Key": token,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": uuid.uuid4().hex,
        }
        return _request_json(DOUBAO_API_URL_V3, json.dumps(payload).encode("utf-8"), headers)

    def _call_v1(v: str) -> Tuple[bytes, str, int]:
        payload = {
            "app": {"appid": appid, "token": token, "cluster": cluster or "volcano_tts"},
            "user": {"uid": "macos-desktop-agent"},
            "audio": _make_audio_payload(v),
            "request": request_payload,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer;{token}",
        }
        return _request_json(DOUBAO_API_URL_V1, json.dumps(payload).encode("utf-8"), headers)

    fallback_voices = [
        "zh_female_shuangkuaisisi_moon_bigtts",
        "zh_male_wennuanahu_moon_bigtts",
        "zh_female_wanwanxiaohe_moon_bigtts",
        "zh_male_jingqiangkanye_moon_bigtts",
    ]
    voice_candidates = [base_voice_type] + [v for v in fallback_voices if v != base_voice_type]

    def _call_v1_candidates() -> Tuple[bytes, str, int, str]:
        last = None
        for v in voice_candidates:
            raw, content_type, status = _call_v1(v)
            data = _parse_response(raw, content_type)
            if isinstance(data, dict):
                audio_b64 = _extract_audio(data)
                code = data.get("code")
                if audio_b64:
                    return raw, content_type, status, v
                if code in (0, "0", None):
                    last = (raw, content_type, status, v)
                    continue
            if status < 400 and not isinstance(data, dict):
                return raw, content_type, status, v
            last = (raw, content_type, status, v)
        if last is None:
            raw, content_type, status = _call_v1(base_voice_type)
            return raw, content_type, status, base_voice_type
        return last

    use_v1_first = _prefer_v1(resource_id, base_voice_type)
    if use_v1_first:
        raw, content_type, status, voice_type = _call_v1_candidates()
    else:
        raw, content_type, status = _call_v3()

    data = _parse_response(raw, content_type)
    if isinstance(data, dict):
        audio_b64 = _extract_audio(data)
        if audio_b64:
            if audio_b64.startswith("http"):
                audio_raw, audio_type, audio_status = _request_json(audio_b64, b"", {})
                if audio_status >= 400:
                    detail = audio_raw.decode("utf-8", errors="ignore")
                    raise RuntimeError(f"豆包TTS音频下载失败：HTTP {audio_status} {detail}")
                fmt = "mp3"
                if "audio/" in audio_type:
                    fmt = audio_type.split("audio/")[1].split(";")[0].strip() or "mp3"
                return audio_raw, fmt
            return base64.b64decode(audio_b64), "mp3"
        code = data.get("code")
        if code not in (0, "0", None):
            message = data.get("message") or "豆包TTS调用失败"
            if use_v1_first:
                if resource_id:
                    raw_v3, content_type_v3, status_v3 = _call_v3()
                    data_v3 = _parse_response(raw_v3, content_type_v3)
                    if isinstance(data_v3, dict):
                        audio_b64 = _extract_audio(data_v3)
                        if audio_b64:
                            return base64.b64decode(audio_b64), "mp3"
                        code_v3 = data_v3.get("code")
                        if code_v3 in (0, "0", None):
                            raise RuntimeError(json.dumps(data_v3, ensure_ascii=False))
                        message_v3 = data_v3.get("message") or "豆包TTS调用失败"
                        raise RuntimeError(f"{message_v3}，当前 voice_type={base_voice_type} 可能与 resource_id={resource_id} 不匹配")
                    if status_v3 >= 400:
                        detail_v3 = raw_v3.decode("utf-8", errors="ignore")
                        raise RuntimeError(f"豆包TTS请求失败：HTTP {status_v3} {detail_v3}")
                raise RuntimeError(f"{message}，请确认 voice_type={voice_type} 在你的账号中可用")
            if resource_id and "resource ID is mismatched" in message and not use_v1_first:
                raw, content_type, status, voice_type = _call_v1_candidates()
                data = _parse_response(raw, content_type)
                if isinstance(data, dict):
                    audio_b64 = _extract_audio(data)
                    if audio_b64:
                        return base64.b64decode(audio_b64), "mp3"
                    code = data.get("code")
                    if code not in (0, "0", None):
                        raise RuntimeError(data.get("message") or f"豆包TTS调用失败(resource_id={resource_id}, voice_type={voice_type})")
                    raise RuntimeError(json.dumps(data, ensure_ascii=False))
            raise RuntimeError(f"{message}(resource_id={resource_id}, voice_type={voice_type})")
        raise RuntimeError(json.dumps(data, ensure_ascii=False))
    if status >= 400:
        detail = raw.decode("utf-8", errors="ignore")
        raise RuntimeError(f"豆包TTS请求失败：HTTP {status} {detail}")
    fmt = "mp3"
    if "audio/" in content_type:
        fmt = content_type.split("audio/")[1].split(";")[0].strip() or "mp3"
    return raw, fmt
