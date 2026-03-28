"""轮询时间线断点：按账号持久化 ``since_id`` 等（JSON 文件，原子写入）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

# username -> { since_id: str, ... }
CheckpointData = Dict[str, Dict[str, str]]


class PollCheckpointStore:
    """
    读写 ``checkpoints.json`` 风格的数据：顶层为 dict，值为 string->string 的内层 dict。

    - ``load``：文件不存在或损坏时返回 ``{}``。
    - ``save``：先写 ``.tmp`` 再 ``replace``，降低进程被 kill 时写坏原文件的概率。
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).expanduser()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> CheckpointData:
        p = self._path
        if not p.is_file():
            return {}
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return {
                    str(k): {str(kk): str(vv) for kk, vv in (v or {}).items()}
                    for k, v in obj.items()
                    if isinstance(v, dict)
                }
        except Exception:
            return {}
        return {}

    def save(self, data: CheckpointData) -> None:
        p = self._path
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
