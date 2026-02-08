from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple
import shutil
import datetime

from .actions import Action
from .utils import expand_user, is_under_any_root, safe_join_dir

class GuardError(Exception):
    pass

class Executor:
    def __init__(self, allowed_roots: List[str]):
        self.allowed_roots = [expand_user(r) for r in allowed_roots]

    def _check_path_allowed(self, p: Path) -> None:
        if not is_under_any_root(p, self.allowed_roots):
            raise GuardError(f"路径不在允许范围内：{p}")

    def preview(self, actions: List[Action]) -> Dict[str, Any]:
        """
        Returns a preview with computed destinations and risk flags.
        """
        out_actions: List[Dict[str, Any]] = []
        risky = False

        for a in actions:
            d = a.to_dict()

            if a.type in ("move", "rename", "ensure_folder", "open_path"):
                if a.src:
                    self._check_path_allowed(expand_user(a.src))
                if a.path:
                    self._check_path_allowed(expand_user(a.path))
                if a.dst_dir:
                    # dst_dir can be under allowed roots; enforce
                    self._check_path_allowed(expand_user(a.dst_dir))

            if a.type == "move":
                src = expand_user(a.src)
                dst_dir = expand_user(a.dst_dir)
                dst = safe_join_dir(dst_dir, src.name)
                d["computed_dst"] = str(dst)
                # risk: overwrite
                if dst.exists():
                    d["risk"] = "high"
                    d["reason"] = "目标已存在，可能覆盖同名文件"
                    risky = True

            if a.type == "rename":
                p = expand_user(a.path)
                dst = safe_join_dir(p.parent, a.new_name)
                d["computed_dst"] = str(dst)
                if dst.exists():
                    d["risk"] = "high"
                    d["reason"] = "重命名目标已存在，可能覆盖同名文件"
                    risky = True
                # extension change risk
                if p.suffix and dst.suffix and p.suffix.lower() != dst.suffix.lower():
                    d["risk"] = "high"
                    d["reason"] = "改变了文件扩展名，属于高风险操作"
                    risky = True

            if a.type == "open_app":
                # low risk by default
                pass

            if a.type == "ensure_folder":
                folder = expand_user(a.path)
                d["computed_path"] = str(folder)
                if folder.exists() and not folder.is_dir():
                    d["risk"] = "high"
                    d["reason"] = "同名路径存在但不是文件夹"
                    risky = True

            out_actions.append(d)

        return {"actions": out_actions, "requires_confirm": risky}

    def execute(self, actions: List[Action], confirm: bool = False) -> Dict[str, Any]:
        prev = self.preview(actions)
        if prev.get("requires_confirm") and not confirm:
            return {"ok": False, "error": "存在高风险操作，需要确认后才能执行", "preview": prev}

        results: List[Dict[str, Any]] = []
        for a in actions:
            try:
                if a.type == "ensure_folder":
                    folder = expand_user(a.path)
                    self._check_path_allowed(folder)
                    folder.mkdir(parents=True, exist_ok=True)
                    results.append({"action": a.to_dict(), "ok": True})

                elif a.type == "move":
                    src = expand_user(a.src)
                    dst_dir = expand_user(a.dst_dir)
                    self._check_path_allowed(src)
                    self._check_path_allowed(dst_dir)
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    dst = safe_join_dir(dst_dir, src.name)
                    shutil.move(str(src), str(dst))
                    results.append({"action": a.to_dict(), "ok": True, "moved_to": str(dst)})

                elif a.type == "rename":
                    p = expand_user(a.path)
                    self._check_path_allowed(p)
                    dst = safe_join_dir(p.parent, a.new_name)
                    p.rename(dst)
                    results.append({"action": a.to_dict(), "ok": True, "renamed_to": str(dst)})

                elif a.type == "open_app":
                    name = a.name
                    result = subprocess.run(["open", "-a", name], capture_output=True, text=True, check=False)
                    if result.returncode == 0:
                        results.append({"action": a.to_dict(), "ok": True})
                    else:
                        err = (result.stderr or result.stdout or "").strip()
                        results.append({"action": a.to_dict(), "ok": False, "error": f"打开应用失败：{name}" + (f"\n{err}" if err else "")})

                elif a.type == "play_music":
                    script = 'tell application "Music"\nactivate\nplay\nend tell'
                    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
                    if result.returncode == 0:
                        results.append({"action": a.to_dict(), "ok": True})
                    else:
                        err = (result.stderr or result.stdout or "").strip()
                        results.append({"action": a.to_dict(), "ok": False, "error": "播放失败" + (f"\n{err}" if err else "")})

                elif a.type == "open_path":
                    p = expand_user(a.path)
                    self._check_path_allowed(p)
                    subprocess.run(["open", str(p)], check=False)
                    results.append({"action": a.to_dict(), "ok": True})

                else:
                    results.append({"action": a.to_dict(), "ok": False, "error": f"未知动作类型：{a.type}"})

            except GuardError as ge:
                results.append({"action": a.to_dict(), "ok": False, "error": f"安全拦截：{ge}"})
            except PermissionError as pe:
                results.append({
                    "action": a.to_dict(),
                    "ok": False,
                    "error": f"权限不足，无法访问路径：{pe}. 请在 macOS 系统设置 > 隐私与安全性 中为运行本服务的终端/应用授权“文件与文件夹”或“完全磁盘访问”。"
                })
            except Exception as e:
                results.append({"action": a.to_dict(), "ok": False, "error": str(e)})

        return {"ok": all(r.get("ok") for r in results), "results": results, "preview": prev}
