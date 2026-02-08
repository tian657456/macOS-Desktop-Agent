from __future__ import annotations
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import unicodedata
import base64

from app.core.planner import Planner
from app.core.executor import Executor
from app.core.actions import Action
from app.core.llm import deepseek_chat
from app.core.doubao_tts import synthesize as doubao_tts

APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent
RULES_PATH = str(BASE_DIR / "config" / "rules.yaml")

planner = Planner(RULES_PATH)
executor = Executor(planner.allowed_roots)

app = FastAPI(title="macOS Desktop Agent", version="0.1.0")

app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

class PlanRequest(BaseModel):
    text: str

class ExecuteRequest(BaseModel):
    actions: List[Dict[str, Any]]
    confirm: bool = False

class ChatMessage(BaseModel):
    role: str
    content: str

class AssistantRequest(BaseModel):
    text: str
    history: List[ChatMessage] = []
    assistant_name: Optional[str] = "小T"

class TTSRequest(BaseModel):
    text: str
    voice_type: Optional[str] = None

def _dict_to_action(d: Dict[str, Any]) -> Action:
    # Accept dicts from client and create Action dataclass
    return Action(**d)

@app.get("/", response_class=HTMLResponse)
def index():
    return (APP_DIR / "static" / "index.html").read_text(encoding="utf-8")

@app.post("/api/plan")
def api_plan(req: PlanRequest):
    planner.reload_rules()
    result = planner.plan(req.text)
    if not result.get("ok"):
        return JSONResponse(status_code=400, content=result)
    actions = result["actions"]
    # Actions are dataclasses
    return {"ok": True, "actions": [a.to_dict() for a in actions], "allowed_roots": planner.allowed_roots}

@app.post("/api/preview")
def api_preview(payload: ExecuteRequest):
    actions = [_dict_to_action(d) for d in payload.actions]
    return executor.preview(actions)

@app.post("/api/execute")
def api_execute(payload: ExecuteRequest):
    actions = [_dict_to_action(d) for d in payload.actions]
    return executor.execute(actions, confirm=payload.confirm)

@app.post("/api/assistant")
def api_assistant(payload: AssistantRequest):
    planner.reload_rules()
    text = payload.text.strip()
    if not text:
        return JSONResponse(status_code=400, content={"ok": False, "error": "请输入指令"})
    plan_result = planner.plan(text)
    actions: List[Action] = []
    preview_data: Dict[str, Any] = {}
    execute_data: Dict[str, Any] = {}
    executed = False
    if plan_result.get("ok"):
        actions = plan_result.get("actions", [])
        preview_data = executor.preview(actions)
        if not preview_data.get("requires_confirm"):
            execute_data = executor.execute(actions, confirm=True)
            executed = execute_data.get("ok", False)
    history_messages = [{"role": m.role, "content": m.content} for m in payload.history]
    is_first_reply = not any(m.role == "assistant" for m in payload.history)
    system_prompt = {
        "role": "system",
        "content": f"你是本地桌面助手，名字叫「{payload.assistant_name}」。风格：温暖、真诚、富有共情，语言更生动但保持简短。允许2到3句短句，不要任何表情符号，不要换行，不要项目符号。若执行成功，先确认再一句轻量关怀或追问；若未执行，先共情再给出原因与下一步建议。若这是首次回复，请自然包含“我是你的桌面助手{payload.assistant_name}”。",
    }
    tool_summary = {
        "role": "system",
        "content": json.dumps({
            "input": text,
            "plan_ok": bool(plan_result.get("ok")),
            "plan_error": plan_result.get("error"),
            "actions": [a.to_dict() for a in actions],
            "preview": preview_data,
            "execute": execute_data,
            "executed": executed,
        }, ensure_ascii=False),
    }
    def _split_sentences(s: str) -> List[str]:
        seps = {"。", "！", "？", ".", "!", "?"}
        parts = []
        start = 0
        for i, ch in enumerate(s):
            if ch in seps:
                seg = s[start:i + 1].strip()
                if seg:
                    parts.append(seg)
                start = i + 1
        tail = s[start:].strip()
        if tail:
            parts.append(tail)
        return parts

    def _dedupe_sentences(parts: List[str]) -> List[str]:
        kept = []
        seen = set()
        for p in parts:
            key = p.replace(" ", "")
            if key in seen:
                continue
            seen.add(key)
            kept.append(p)
        return kept

    def _remove_intro_duplicate(parts: List[str], name: Optional[str]) -> List[str]:
        if not name:
            return parts
        intro = f"我是你的桌面助手{name}"
        kept = []
        found = False
        for p in parts:
            if intro in p:
                if found:
                    continue
                found = True
            kept.append(p)
        return kept

    def _sanitize(s: str, name: Optional[str] = None) -> str:
        clean = "".join(ch for ch in s if unicodedata.category(ch) != "So")
        clean = clean.replace("\n", " ").replace("\r", " ")
        clean = " ".join(clean.split())
        parts = _split_sentences(clean)
        parts = _dedupe_sentences(parts)
        parts = _remove_intro_duplicate(parts, name)
        if parts:
            return "".join(parts[:2]).strip()
        return clean.strip()

    try:
        reply_raw = deepseek_chat([system_prompt] + history_messages + [{"role": "user", "content": text}] + [tool_summary], temperature=0.85)
        reply = _sanitize(reply_raw, payload.assistant_name)
        if is_first_reply and payload.assistant_name:
            intro = f"我是你的桌面助手{payload.assistant_name}"
            if intro not in reply:
                reply = _sanitize(f"你好，{intro}。{reply}", payload.assistant_name)
            else:
                reply = _sanitize(reply, payload.assistant_name)
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
    return {
        "ok": True,
        "reply": reply,
        "actions": [a.to_dict() for a in actions],
        "preview": preview_data,
        "execute": execute_data,
        "executed": executed,
    }

@app.post("/api/tts")
def api_tts(payload: TTSRequest):
    text = payload.text.strip()
    if not text:
        return JSONResponse(status_code=400, content={"ok": False, "error": "请输入文本"})
    try:
        audio, fmt = doubao_tts(text, voice_type=payload.voice_type)
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
    return {"ok": True, "audio_base64": base64.b64encode(audio).decode("utf-8"), "format": fmt}

@app.get("/api/rules")
def api_rules():
    return {"rules_path": RULES_PATH, "allowed_roots": planner.allowed_roots}
