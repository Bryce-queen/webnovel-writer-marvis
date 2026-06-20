#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chapter commit CLI — 原子提交链。

单次调用自动执行：预检 → 评分落库 → 提交 → 投影 → 后检 → 日志。
外部无需再分别调用 write-gate / review-pipeline / run-log，物理杜绝漏跑。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio

from data_modules.chapter_commit_service import ChapterCommitService
from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager


def _read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _die(report: dict) -> None:
    """打印阻断报告并退出。"""
    errors = report.get("errors") or []
    print(json.dumps({"blocked": True, "stage": report.get("stage"), "errors": errors}, ensure_ascii=False, indent=2), file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chapter commit CLI（原子提交链）")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--review-result", required=True)
    parser.add_argument("--fulfillment-result", required=True)
    parser.add_argument("--disambiguation-result", required=True)
    parser.add_argument("--extraction-result", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root)
    chapter = args.chapter

    # ── 1. 预检（write-gate --precommit） ──
    from data_modules import write_gates
    pre = write_gates.run_write_gate(project_root, chapter=chapter, stage="precommit")
    if pre.get("status") == "block":
        _die(pre)

    # ── 2. 审查评分落库（review-pipeline） ──
    from review_pipeline import _build_review_metrics_record, build_review_artifacts
    artifacts = build_review_artifacts(
        project_root=project_root,
        chapter=chapter,
        review_results_path=Path(args.review_result),
        report_file="",
    )
    config = DataModulesConfig.from_project_root(project_root)
    manager = IndexManager(config)
    manager.save_review_metrics(_build_review_metrics_record(artifacts["metrics"]))

    # ── 3. 提交 ──
    service = ChapterCommitService(project_root)
    payload = service.build_commit(
        chapter=chapter,
        review_result=_read_json(args.review_result),
        fulfillment_result=_read_json(args.fulfillment_result),
        disambiguation_result=_read_json(args.disambiguation_result),
        extraction_result=_read_json(args.extraction_result),
    )
    service.persist_commit(payload)
    payload = service.apply_projections(payload)

    # ── 4. 后检（write-gate --postcommit） ──
    post = write_gates.run_write_gate(project_root, chapter=chapter, stage="postcommit")
    post_status = str(post.get("status") or "")
    if post_status == "block":
        _die(post)

    # ── 5. 运行日志 ──
    from data_modules.run_logger import write_run_log
    write_run_log(
        project_root,
        event="chapter_commit",
        payload={
            "chapter": chapter,
            "commit_status": str((payload.get("meta") or {}).get("status") or ""),
            "review_score": artifacts["metrics"].get("overall_score"),
            "precommit_status": pre.get("status"),
            "postcommit_status": post.get("status"),
        },
    )

    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
