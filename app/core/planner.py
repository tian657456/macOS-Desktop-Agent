from __future__ import annotations
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import yaml

from .actions import Action
from .utils import expand_user, is_hidden

# Simple Chinese command parsing + rules-based planning.
# You can later replace this with an LLM planner that outputs the same Action JSON.

MOVE_PATTERN = re.compile(
    r"(?:把|将)\s*(?P<file>.+?)\s*(?:放到|放入|放进|移动到|移到|移动至|移至)\s*(?P<folder>.+?)(?:\s*(?:并)?(?:重命名为|重命名成|改名为|改名成)\s*(?P<newname>.+))?\s*$"
)
OPEN_MUSIC_PLAY_PATTERN = re.compile(r"(?:打开)?音乐.*(?:自动播放|播放).*$")
OPEN_APP_PATTERN = re.compile(r"(?:打开软件|打开|打开应用)\s*(?P<app>.+?)\s*$")
OPEN_PATH_PATTERN = re.compile(r"(?:打开路径|打开文件夹|打开目录)\s*(?P<path>.+?)\s*$")

class Planner:
    def __init__(self, rules_path: str):
        self.rules_path = rules_path
        self.reload_rules()

    def reload_rules(self) -> None:
        p = Path(self.rules_path)
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        self.allowed_roots = data.get("allowed_roots", ["~/Desktop", "~/Documents", "~/Downloads"])
        self.keyword_rules = data.get("keyword_rules", [])
        self.extension_rules = data.get("extension_rules", {})
        self.skip_hidden = bool(data.get("skip_hidden", True))
        self.skip_directories = bool(data.get("skip_directories", True))
        self.batch_risk_threshold = int(data.get("batch_risk_threshold", 20))

    def plan(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        if not text:
            return {"ok": False, "error": "请输入指令"}

        # 1) explicit open path
        m = OPEN_PATH_PATTERN.match(text)
        if m:
            path = m.group("path").strip()
            return {"ok": True, "actions": [Action(type="open_path", path=path)]}

        # 2) explicit move + optional rename
        m = MOVE_PATTERN.match(text)
        if m:
            file_name = m.group("file").strip().strip('"').strip("'")
            folder = self._resolve_input_folder(m.group("folder").strip().strip('"').strip("'"))
            newname = m.group("newname")
            # interpret file as Desktop relative if no slash and not startswith ~
            src = self._resolve_input_file(file_name)
            actions = [Action(type="ensure_folder", path=folder),
                       Action(type="move", src=str(src), dst_dir=folder)]
            if newname:
                # rename after move: rename path becomes inside folder
                dst_path = str(expand_user(folder) / src.name)
                actions.append(Action(type="rename", path=dst_path, new_name=newname.strip()))
            return {"ok": True, "actions": actions}

        # 3) open music and play
        m = OPEN_MUSIC_PLAY_PATTERN.match(text)
        if m:
            return {"ok": True, "actions": [Action(type="play_music")]}

        # 4) open app (note: ambiguous with "打开路径")
        m = OPEN_APP_PATTERN.match(text)
        if m and not text.startswith("打开路径"):
            app = self._resolve_app_name(m.group("app").strip())
            return {"ok": True, "actions": [Action(type="open_app", name=app)]}

        # 5) organize desktop
        if any(k in text for k in ("整理桌面", "整理一下桌面", "整理桌面文件", "整理桌面并分类", "整理桌面文件并分类", "分类桌面", "分类桌面文件")):
            return {"ok": True, "actions": self._plan_organize_desktop()}

        return {"ok": False, "error": "无法解析指令。可试试：整理桌面文件并分类 / 把 XXX 移动到 YYY 并重命名为 ZZZ / 打开软件 AppName / 打开路径 /path"}

    def _resolve_input_file(self, file_name: str) -> Path:
        if "/" in file_name or file_name.startswith("~"):
            return expand_user(file_name)
        base_dir, name = self._split_location_prefix(file_name)
        if base_dir:
            return self._resolve_existing_file(expand_user(base_dir), name)
        return self._resolve_existing_file(expand_user("~/Desktop"), file_name)

    def _resolve_input_folder(self, folder: str) -> str:
        if "/" in folder or folder.startswith("~"):
            return folder
        folder = self._normalize_folder_text(folder)
        base_dir, name = self._split_location_prefix(folder)
        if base_dir and name:
            return str((expand_user(base_dir) / name).resolve())
        if base_dir and not name:
            return str(expand_user(base_dir))
        existing = self._resolve_existing_folder(folder)
        if existing:
            return existing
        if folder in ("桌面", "桌面上", "桌面里", "桌面中"):
            return str(expand_user("~/Desktop"))
        if folder in ("文稿", "文档", "文稿里", "文稿中", "文档里", "文档中"):
            return str(expand_user("~/Documents"))
        if folder in ("下载", "下载目录", "下载文件夹", "下载里", "下载中"):
            return str(expand_user("~/Downloads"))
        return str((expand_user("~/Documents") / folder).resolve())

    def _split_location_prefix(self, text: str) -> Tuple[Optional[str], str]:
        pattern = re.compile(
            r"^(?P<loc>桌面|文稿|文档|下载|下载目录|下载文件夹)(?:下的|里的|中的|下面的|上面的|上的|上面|下面|上|下|里|中)?\s*(?P<name>.*)$"
        )
        m = pattern.match(text.strip())
        if not m:
            return None, text
        loc = m.group("loc")
        name = (m.group("name") or "").strip()
        if loc == "桌面":
            return "~/Desktop", name
        if loc in ("文稿", "文档"):
            return "~/Documents", name
        if loc in ("下载", "下载目录", "下载文件夹"):
            return "~/Downloads", name
        return None, text

    def _resolve_existing_file(self, base_dir: Path, name: str) -> Path:
        candidate = (base_dir / name).resolve()
        if candidate.exists():
            return candidate
        if base_dir.exists():
            matches = [p for p in base_dir.iterdir() if p.name == name or p.stem == name]
            if len(matches) == 1:
                return matches[0].resolve()
        return candidate

    def _normalize_folder_text(self, text: str) -> str:
        t = text.strip()
        t = re.sub(r"(文件夹)?(下面|下|里|中)?$", "", t).strip()
        return t

    def _resolve_existing_folder(self, name: str) -> Optional[str]:
        for base in ("~/Desktop", "~/Documents", "~/Downloads"):
            base_path = expand_user(base)
            candidate = (base_path / name).resolve()
            if candidate.exists() and candidate.is_dir():
                return str(candidate)
        return None

    def _resolve_app_name(self, name: str) -> str:
        key = name.strip().lower()
        aliases = {
            "音乐": "Music",
            "音乐app": "Music",
            "apple music": "Music",
            "日历": "Calendar",
            "备忘录": "Notes",
            "提醒事项": "Reminders",
            "通讯录": "Contacts",
            "日程": "Calendar",
            "邮件": "Mail",
            "邮件.app": "Mail",
            "计算器": "Calculator",
            "终端": "Terminal",
            "系统设置": "System Settings",
            "系统偏好设置": "System Settings",
            "相册": "Photos",
        }
        return aliases.get(key, name.strip())

    def _match_keyword_rule(self, filename: str) -> Optional[str]:
        low = filename.lower()
        for rule in self.keyword_rules:
            kws = rule.get("keywords", [])
            dst = rule.get("dst_dir")
            for kw in kws:
                if kw and kw.lower() in low:
                    return dst
        return None

    def _match_extension_rule(self, path: Path) -> Optional[str]:
        ext = path.suffix.lower().lstrip(".")
        if not ext:
            return None
        return self.extension_rules.get(ext)

    def _plan_organize_desktop(self) -> List[Action]:
        desktop = expand_user("~/Desktop")
        actions: List[Action] = []
        candidates: List[Path] = []

        for p in desktop.iterdir():
            if self.skip_hidden and is_hidden(p):
                continue
            if self.skip_directories and p.is_dir():
                continue
            candidates.append(p)

        for p in candidates:
            dst = self._match_keyword_rule(p.name)
            if not dst:
                dst = self._match_extension_rule(p)
            if not dst:
                continue  # unclassified: leave in place

            actions.append(Action(type="ensure_folder", path=dst))
            actions.append(Action(type="move", src=str(p), dst_dir=dst))

        # batch risk marking
        if len(actions) >= self.batch_risk_threshold * 2:  # each file -> 2 actions
            for a in actions:
                if a.type in ("move", "rename"):
                    a.risk = "high"
                    a.reason = f"批量操作较多（>{self.batch_risk_threshold} 个文件），建议确认后执行"
        return actions
