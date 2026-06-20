#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio

from data_modules.chapter_commit_service import ChapterCommitService


def _read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Chapter commit CLI")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--review-result", required=True)
    parser.add_argument("--fulfillment-result", required=True)
    parser.add_argument("--disambiguation-result", required=True)
    parser.add_argument("--extraction-result", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root)

    # 内置审查 Pipeline：计算评分与指标并写入 index.db，确保不可能漏跑
    from review_pipeline import _build_review_metrics_record, build_review_artifacts
    artifacts = build_review_artifacts(
        project_root=project_root,
        chapter=args.chapter,
        review_results_path=Path(args.review_result),
        report_file="",
    )
    from data_modules.config import DataModulesConfig
    from data_modules.index_manager import IndexManager
    config = DataModulesConfig.from_project_root(project_root)
    manager = IndexManager(config)
    manager.save_review_metrics(_build_review_metrics_record(artifacts["metrics"]))

    service = ChapterCommitService(project_root)
    payload = service.build_commit(
        chapter=args.chapter,
        review_result=_read_json(args.review_result),
        fulfillment_result=_read_json(args.fulfillment_result),
        disambiguation_result=_read_json(args.disambiguation_result),
        extraction_result=_read_json(args.extraction_result),
    )
    service.persist_commit(payload)
    payload = service.apply_projections(payload)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
