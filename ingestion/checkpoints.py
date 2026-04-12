"""轮询断点：JSON 文件、原子写入；支持多数据源命名空间（X 时间线、财联社电报等）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, MutableMapping

JsonDict = Dict[str, Any]


def migrate_checkpoint_root(obj: JsonDict) -> JsonDict:
    """
    旧格式：顶层键为 X 账号名，值为 ``{since_id: ...}``。
    新格式：``{"x": {username: {...}}, "cls_telegraph": {...}}``。
    """
    if not obj:
        return {"x": {}, "cls_telegraph": {}}
    if "x" in obj and isinstance(obj.get("x"), dict):
        out = dict(obj)
        out.setdefault("x", {})
        if "cls_telegraph" not in out or not isinstance(out.get("cls_telegraph"), dict):
            out["cls_telegraph"] = {}
        return out
    # 旧：仅 X 账号
    only_x: JsonDict = {}
    reserved = {"x", "cls_telegraph", "version"}
    for k, v in obj.items():
        if k in reserved:
            continue
        if isinstance(v, dict):
            only_x[str(k)] = dict(v)
    return {"x": only_x, "cls_telegraph": {}}


class PollCheckpointStore:
    """
    读写 checkpoints JSON：顶层为 dict，可嵌套（``x`` / ``cls_telegraph`` 等）。

    - ``load``：文件不存在或损坏时返回经 migrate 的空结构。
    - ``save``：先写 ``.tmp`` 再 ``replace``。
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).expanduser()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> JsonDict:
        p = self._path
        if not p.is_file():
            return migrate_checkpoint_root({})
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return migrate_checkpoint_root(obj)
        except Exception:
            return migrate_checkpoint_root({})
        return migrate_checkpoint_root({})

    def save(self, data: MutableMapping[str, Any]) -> None:
        p = self._path
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(dict(data), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
