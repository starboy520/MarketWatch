from __future__ import annotations

from ingestion.checkpoints import migrate_checkpoint_root


def test_migrate_old_x_only_checkpoint() -> None:
    old = {"business": {"since_id": "123"}}
    out = migrate_checkpoint_root(old)
    assert out["x"]["business"]["since_id"] == "123"
    assert out["cls_telegraph"] == {}


def test_migrate_passthrough_v2() -> None:
    v2 = {"x": {"a": {"since_id": "1"}}, "cls_telegraph": {"bootstrapped": "1"}}
    out = migrate_checkpoint_root(v2)
    assert out == v2
