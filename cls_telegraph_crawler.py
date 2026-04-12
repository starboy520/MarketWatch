#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容入口：财联社电报调试 CLI。实现已迁至 ``ingestion.sources.cls_telegraph``。"""

from __future__ import annotations

from ingestion.sources.cls_telegraph import run_cli

if __name__ == "__main__":
    run_cli()
