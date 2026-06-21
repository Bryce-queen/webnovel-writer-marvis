#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt 完整性静态校验。

验证 skills/*/SKILL.md 的结构、引用、CLI 命令等，
不需要 LLM 调用，可加入 CI。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 基础路径
# ---------------------------------------------------------------------------

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SKILLS_DIR = PLUGIN_ROOT / "skills"
REFERENCES_DIR = PLUGIN_ROOT / "references"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"

# AGENTS_DIR removed in v1.0.19 — all sub-agents migrated to dispatch_task("file-agent")
SKILL_FILES = sorted(SKILLS_DIR.glob("*/SKILL.md"))
ALL_PROMPT_FILES = SKILL_FILES
AUTHOR_REPORT_SKILLS = (
    "webnovel-init",
    "webnovel-plan",
    "webnovel-write",
    "webnovel-review",
)
SUBAGENT_RUN_FIELDS = (
    '"status": "completed | partial | failed | skipped"',
    '"problems": []',
    '"auto_handled": []',
    '"needs_user_action": false',
    '"duration_ms": 0',
    '"outputs": []',
)
# SUBAGENT_PROMPT_FILES removed in v1.0.19 — agents migrated to dispatch_task("file-agent")

# webnovel.py 注册的子命令（从 add_parser 提取）
REGISTERED_CLI_SUBCOMMANDS = {
    "where", "preflight", "project-status", "doctor", "write-gate", "projections", "user-report",
    "run-ledger", "run-log", "use",
    "index", "state", "rag", "style", "entity", "context", "memory",
    "migrate", "status", "update-state", "backup", "archive",
    "init", "extract-context", "memory-contract", "project-memory", "review-pipeline",
    "placeholder-scan", "master-outline-sync",
    "story-system", "chapter-commit", "story-events", "knowledge",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_frontmatter(text: str) -> dict:
    """提取 YAML frontmatter 为 dict。"""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    result = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def _extract_referenced_paths(text: str, base_dir: Path) -> list[tuple[str, Path]]:
    """从 markdown 中提取被引用的文件路径（references/, skills/, agents/ 等）。

    返回 (raw_ref, resolved_path) 列表。
    """
    refs = []
    # 匹配 `references/xxx.md`、`../../references/xxx.md`、`skills/xxx` 等相对路径
    for m in re.finditer(r'[`"]((?:\.\./)*(?:references|skills|agents)/[^\s`"]+\.md)[`"]', text):
        raw = m.group(1)
        resolved = (base_dir / raw).resolve()
        refs.append((raw, resolved))
    # 匹配 references 段落中列出的路径（不带引号）
    for m in re.finditer(r'^- `((?:\.\./)*(?:references|skills|agents)/[^\s`]+\.md)`', text, re.MULTILINE):
        raw = m.group(1)
        resolved = (base_dir / raw).resolve()
        refs.append((raw, resolved))
    return refs


def _extract_cli_subcommands(text: str) -> list[str]:
    """从 prompt 中提取 webnovel.py 调用的子命令。"""
    cmds = set()
    for m in re.finditer(r'webnovel\.py["\s]+--project-root\s+[^\s]+\s+([a-z][\w-]*)', text):
        cmd = m.group(1)
        cmds.add(cmd)
    return sorted(cmds)


# ---------------------------------------------------------------------------
# 1. Frontmatter 完整性
# ---------------------------------------------------------------------------


def test_skill_frontmatter_complete(skill_file: Path):
    """每个 skill 必须有 name, description。"""
    fm = _extract_frontmatter(_read_text(skill_file))
    assert "name" in fm, f"{skill_file.parent.name}: 缺少 name"
    assert "description" in fm, f"{skill_file.parent.name}: 缺少 description"


# ---------------------------------------------------------------------------
# 2. Agent 模板结构（≥4 段）
# ---------------------------------------------------------------------------

EXPECTED_AGENT_SECTIONS = [
    "1.",
    "2.",
    "3.",
    "4.",
]


def test_all_references_exist(prompt_file: Path):
    """prompt 中引用的所有文件路径都必须真实存在。"""
    text = _read_text(prompt_file)
    base_dir = prompt_file.parent
    refs = _extract_referenced_paths(text, base_dir)
    missing = []
    for raw, resolved in refs:
        if not resolved.exists():
            missing.append(raw)
    assert not missing, f"{prompt_file.name}: 引用了不存在的文件 {missing}"


# ---------------------------------------------------------------------------
# 4. CLI 命令有效性
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prompt_file", ALL_PROMPT_FILES, ids=lambda f: f.name)
def test_cli_commands_valid(prompt_file: Path):
    """prompt 中的 webnovel.py 子命令都必须在 CLI 注册表中。"""
    text = _read_text(prompt_file)
    cmds = _extract_cli_subcommands(text)
    # 排除已知例外（如 webnovel-review 的 workflow 命令待重构）
    skill_name = prompt_file.parent.name
    exceptions = _KNOWN_CLI_EXCEPTIONS.get(skill_name, set())
    invalid = [c for c in cmds if c not in REGISTERED_CLI_SUBCOMMANDS and c not in exceptions]
    assert not invalid, f"{prompt_file.name}: 使用了未注册的 CLI 子命令 {invalid}"


# ---------------------------------------------------------------------------
# 5. Review Schema 一致性
# ---------------------------------------------------------------------------


def test_no_stale_references(prompt_file: Path):
    """不得引用已知已删除的文件。"""
    text = _read_text(prompt_file)
    found = [name for name in KNOWN_DELETED_FILES if name in text]
    assert not found, f"{prompt_file.name}: 残留引用已删除文件 {found}"


def test_webnovel_review_skill_uses_unified_reviewer_pipeline():
    """webnovel-review 必须与 webnovel-write 使用同一套 reviewer + review-pipeline 链路。"""
    skill_text = _read_text(SKILLS_DIR / "webnovel-review" / "SKILL.md")

    assert "dispatch_task" in skill_text
    assert "dispatch_task(" in skill_text
    assert "subagent_type:" not in skill_text
    assert "review-pipeline" in skill_text
    assert ".webnovel/tmp/review_results.json" in skill_text
    assert ".webnovel/tmp/review_metrics.json" in skill_text

    for legacy_agent in (
        "consistency-checker",
        "continuity-checker",
        "ooc-checker",
        "reader-pull-checker",
        "high-point-checker",
        "pacing-checker",
    ):
        assert legacy_agent not in skill_text

    assert " workflow " not in skill_text


def test_active_skills_use_agent_tool_name_not_legacy_task():
    """Claude Code 2.1.63+ 将 Task 工具改名为 Agent；active skills 不应再声明 Task。"""
    for skill_file in SKILL_FILES:
        text = _read_text(skill_file)
        fm = _extract_frontmatter(text)
        allowed_tools = fm.get("allowed-tools", "")
        assert "Task" not in allowed_tools, f"{skill_file.parent.name}: allowed-tools 仍声明 Task"
        assert "Task 调用" not in text, f"{skill_file.parent.name}: 仍使用软性的 Task 调用描述"
        assert "必须通过 `Task`" not in text, f"{skill_file.parent.name}: 仍要求旧 Task 工具名"


def test_webnovel_write_skill_uses_explicit_dispatch_task_calls():
    """v1.0.19: 关键 subagent 全部经 dispatch_task("file-agent") 调用。"""
    text = _read_text(SKILLS_DIR / "webnovel-write" / "SKILL.md")
    fm = _extract_frontmatter(text)

    assert "dispatch_task" in fm.get("allowed-tools", "")
    assert 'dispatch_task(' in text, "缺少 dispatch_task 调用"
    assert 'agent_name="file-agent"' in text, "缺少 file-agent 派发"
    assert "file-agent" in text, "不应再使用伪函数 subagent_type 调用块"
    assert "不得用主流程口头代替 subagent 输出" in text


@pytest.mark.parametrize("skill_name", AUTHOR_REPORT_SKILLS)
def test_main_skills_define_author_friendly_final_report_contract(skill_name: str):
    """四个主 Skill 必须提供作者友好的总状态 + 三段式最终报告契约。"""
    text = _read_text(SKILLS_DIR / skill_name / "SKILL.md")

    assert "作者友好最终报告契约" in text
    assert "总状态：已完成 / 部分完成 / 需要你处理 / 未完成" in text
    for section in (
        "一、产生的文件与完成情况",
        "二、过程中遇到的问题与异常耗时",
        "三、下一步建议",
    ):
        assert section in text, f"{skill_name}: 缺少最终报告段落 {section}"
    for issue_type in ("已自动处理", "建议确认", "必须处理"):
        assert issue_type in text, f"{skill_name}: 缺少异常分类 {issue_type}"
    assert "任务化语言" in text
    assert "可复制命令" in text
    assert "/webnovel-doctor" in text
    assert "不写 token 统计" in text


def test_write_skill_final_report_covers_commit_projection_and_backup():
    """写章最终报告必须覆盖正文、审查、data artifacts、commit、projection、backup。"""
    text = _read_text(SKILLS_DIR / "webnovel-write" / "SKILL.md")
    for required in (
        "正文文件路径",
        "审查报告路径",
        ".webnovel/tmp/review_results.json",
        ".webnovel/tmp/fulfillment_result.json",
        ".webnovel/tmp/disambiguation_result.json",
        ".webnovel/tmp/extraction_result.json",
        ".story-system/commits/chapter_{NNN}.commit.json",
        "state / index / summary / memory / vector 更新状态",
        "备份状态",
        "是否可以继续写下一章",
    ):
        assert required in text
    assert "chapter-commit rejected" in text
    assert "最终状态不得写“已完成”" in text
    assert "--fast" in text and "--minimal" in text
    assert "projection retry" in text


def test_review_skill_final_report_covers_metrics_and_blocking_decision():
    """审查最终报告必须覆盖报告、metrics、blocking 数与用户裁决状态。"""
    text = _read_text(SKILLS_DIR / "webnovel-review" / "SKILL.md")
    for required in (
        "审查报告文件",
        ".webnovel/tmp/review_results.json",
        ".webnovel/tmp/review_metrics.json",
        "review_metrics",
        "阻断问题数量",
        "用户裁决状态",
        "如果无阻断，明确可以继续写作",
    ):
        assert required in text
    assert "有 blocking 问题且用户未选择处理策略" in text
    assert "最终状态为“需要你处理”" in text


def test_main_skills_record_subagent_run_summaries_for_agent_calls():
    """主 Skill 调用 Agent 后必须记录 SubagentRun 汇总，供最终报告使用。"""
    expected = {
        "webnovel-init": ("file-agent",),
        "webnovel-write": ("file-agent",),
        "webnovel-review": ("file-agent",),
    }

    for skill_name, agents in expected.items():
        text = _read_text(SKILLS_DIR / skill_name / "SKILL.md")
        assert "SubagentRun" in text, f"{skill_name}: 缺少 SubagentRun 汇总契约"
        for field in SUBAGENT_RUN_FIELDS:
            assert field in text, f"{skill_name}: 缺少 SubagentRun 字段 {field}"
        for agent_name in agents:
            assert f'"name": "{agent_name}"' in text, (
                f"{skill_name}: 缺少 {agent_name} 的 SubagentRun name"
            )
    plan_text = _read_text(SKILLS_DIR / "webnovel-plan" / "SKILL.md")
    assert "SubagentRun" not in plan_text, "webnovel-plan 当前不调用 Agent，不应虚构 SubagentRun"


def test_main_skills_define_author_friendly_progress_and_recovery_contract(skill_name: str):
    """四个主 Skill 必须有过程提示、少打扰确认、卡住恢复和日志边界。"""
    text = _read_text(SKILLS_DIR / skill_name / "SKILL.md")

    for required in (
        "作者友好过程提示与恢复契约",
        "过程提示",
        "少打扰确认策略",
        "有限选项",
        "卡住时必须说明",
        "卡点",
        "已完成内容",
        "恢复建议",
        ".webnovel/logs/run_last.log",
        "run-log",
        "user-report",
    ):
        assert required in text, f"{skill_name}: 缺少过程/恢复契约 {required}"
    assert "不直接输出原始 JSON" in text or "不输出原始 JSON" in text


def test_write_skill_progress_nodes_are_author_friendly_and_limited():
    """写章过程节点必须压缩到不超过 6 个作者可理解阶段。"""
    text = _read_text(SKILLS_DIR / "webnovel-write" / "SKILL.md")
    marker = "写章过程节点（最多 6 个）"
    assert marker in text
    section = text[text.find(marker): text.find("## 充分性闸门")]
    nodes = re.findall(r"^\d+\.\s+(.+)$", section, flags=re.MULTILINE)
    assert 1 <= len(nodes) <= 6
    for forbidden in ("write-gate", "chapter-commit", "projection_status", "artifact", "schema"):
        assert forbidden not in "\n".join(nodes)
    for friendly in ("检查项目环境", "整理写作依据", "起草正文", "写作检查", "保存本章故事事实", "提交备份"):
        assert any(friendly in node for node in nodes), f"缺少作者友好节点 {friendly}"


def test_write_skill_resume_contract_uses_runtime_ledger_and_confirmation_boundaries():
    """写章重复执行必须先查可信断点，且在覆盖风险处停下确认。"""
    text = _read_text(SKILLS_DIR / "webnovel-write" / "SKILL.md")
    for required in (
        "run-ledger write-resume",
        "可信断点",
        "正文被手动改过",
        "章纲更新晚于正文",
        "本章已 accepted",
        "沿用当前正文 / 重新起草 / 只查看状态",
        "不得覆盖作者手改",
    ):
        assert required in text


def test_story_system_runtime_contract_commands_exist():
    text = (SKILLS_DIR / "webnovel-write" / "SKILL.md").read_text(encoding="utf-8")
    assert "story-system" in text
    assert "--emit-runtime-contracts" in text


def test_webnovel_write_skill_uses_chapter_commit_as_step5_mainline():
    text = (SKILLS_DIR / "webnovel-write" / "SKILL.md").read_text(encoding="utf-8")
    assert "chapter-commit" in text
    assert "CHAPTER_COMMIT" in text
    assert "state process-chapter" not in text


def test_webnovel_write_skill_uses_project_root_backup_not_bare_git_add():
    text = (SKILLS_DIR / "webnovel-write" / "SKILL.md").read_text(encoding="utf-8")
    assert "webnovel.py" in text
    assert "--project-root \"{PROJECT_ROOT}\" backup" in text
    assert "git add ." not in text


def test_webnovel_query_skill_prefers_story_system_and_memory_contract():
    text = (SKILLS_DIR / "webnovel-query" / "SKILL.md").read_text(encoding="utf-8")
    assert "memory-contract load-context" in text
    assert ".story-system/" in text
    assert 'cat "$PROJECT_ROOT/.webnovel/state.json"' not in text


def test_dashboard_and_plan_skills_surface_story_runtime_mainline():
    dashboard_text = (SKILLS_DIR / "webnovel-dashboard" / "SKILL.md").read_text(encoding="utf-8")
    plan_text = (SKILLS_DIR / "webnovel-plan" / "SKILL.md").read_text(encoding="utf-8")
    assert "story-runtime/health" in dashboard_text
    assert ".story-system/" in plan_text


def test_webnovel_write_skill_routes_step2_through_writing_brief():
    text = (SKILLS_DIR / "webnovel-write" / "SKILL.md").read_text(encoding="utf-8")
    assert "写作任务书" in text
    assert "file-agent" in text
    assert "Step 0.5" not in text
    assert 'cat "${SKILL_ROOT}/../../references/shared/core-constraints.md"' not in text
    assert 'cat "${SKILL_ROOT}/references/anti-ai-guide.md"' not in text


def test_no_direct_state_writes_in_write_skill():
    """webnovel-write SKILL.md 中不应有 set-chapter-status 调用。"""
    text = (SKILLS_DIR / "webnovel-write" / "SKILL.md").read_text(encoding="utf-8")
    assert "state set-chapter-status" not in text, (
        "webnovel-write 中不应直接调用 state set-chapter-status，"
        "chapter_status 由 state_projection_writer 在 commit 时自动推进"
    )


def test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate():
    """init may consume only confirmed, transformed reference patterns."""
    text = _read_text(SKILLS_DIR / "webnovel-init" / "SKILL.md")

    assert "dispatch_task(" in text and "file-agent" in text
    assert "file-agent" in text
    assert "dispatch_task(" in text or "Step 1.5" in text
    assert "进入故事核采集前" in text
    assert "不要默认拆书" in text
    assert "你这本书的灵感来源想从哪里开始" in text
    assert "init_reference_research" in text
    assert "init_reference_research" in text
    assert ".webnovel/tmp/reference_analyses/<safe-title>/" not in text
    assert "project_root=${PROJECT_ROOT" not in text
    assert "不写任何文件" in text
    assert "不得由 init 主流程口头替代拆解结果" in text
    assert "`quality`" in text
    assert "`quality.passed=false`" in text
    assert "`confidence < 0.85`" in text

    for handoff_field in (
        "reader_promise",
        "opening_hook_patterns",
        "cool_point_loops",
        "protagonist_patterns",
        "antagonist_pressure_patterns",
        "pacing_notes",
        "borrowable_structures",
        "differentiation_requirements",
        "init_candidates",
    ):
        assert handoff_field in text

    for forbidden_path in (
        "idea_bank.json",
        ".story-system",
        "设定集",
        "大纲",
        "正文",
        ".webnovel/state.json",
    ):
        assert forbidden_path in text

    assert "用户确认前" in text
    assert "Step 2-6 只能使用用户确认过、并已变形为本书差异化表达的模式" in text
    assert "汇总 Step 1.5 已确认的灵感来源" in text


# ---------------------------------------------------------------------------
# 7. A 类跨层红线：行为/契约级断言（Phase 0 守护）
#    这些断言守护「已实现」的业务红线，全部应为绿。优先断言结构不变量
#    （命令存在/顺序、节点 schema、变量化的真实参数），不做脆弱的文案匹配。
# ---------------------------------------------------------------------------

# A 类红线 2：placeholder-scan 必须出现在 plan 与 write 两层的关键节点。
def test_placeholder_scan_runs_in_both_plan_and_write_skills():
    """红线 2：plan 与 write 都必须显式调用 placeholder-scan CLI。"""
    plan_text = _read_text(SKILLS_DIR / "webnovel-plan" / "SKILL.md")
    write_text = _read_text(SKILLS_DIR / "webnovel-write" / "SKILL.md")
    for name, text in (("webnovel-plan", plan_text), ("webnovel-write", write_text)):
        cmds = _extract_cli_subcommands(text)
        assert "placeholder-scan" in cmds, (
            f"{name}: 关键节点缺少 placeholder-scan CLI 调用"
        )


# A 类红线 3：story-system 章级刷新必须传入真实 CHAPTER_GOAL 变量，
# 不得把 {章纲目标} / 第N章章纲目标 这类占位文本当作 positional query。
@pytest.mark.parametrize("skill_name", ["webnovel-plan", "webnovel-write"])
def test_story_system_chapter_refresh_uses_real_goal_not_placeholder_query(skill_name: str):
    """红线 3：story-system 的 query 实参是 ${CHAPTER_GOAL} 变量，且禁占位文本写在命令里。"""
    text = _read_text(SKILLS_DIR / skill_name / "SKILL.md")
    # 命令必须用变量化的真实目标作为 query 实参
    assert 'story-system "${CHAPTER_GOAL}"' in text, (
        f"{skill_name}: story-system 未使用真实 ${{CHAPTER_GOAL}} 作为 query 实参"
    )
    # 占位 query 绝不能作为 story-system 的 positional 实参出现
    for placeholder in ("{章纲目标}", "第N章章纲目标"):
        assert f'story-system "{placeholder}"' not in text, (
            f"{skill_name}: story-system 不得把占位文本 {placeholder} 当作 query"
        )
    # 必须显式声明「禁止占位 query」这一约束（断言事实存在，不锁具体措辞）
    assert "{章纲目标}" in text and "第N章章纲目标" in text, (
        f"{skill_name}: 缺少对占位 query 的明确禁止说明"
    )


# A 类红线 4：story-system 章级刷新必须 --persist 且 --emit-runtime-contracts。
@pytest.mark.parametrize("skill_name", ["webnovel-plan", "webnovel-write"])
def test_story_system_chapter_refresh_persists_runtime_contracts(skill_name: str):
    """红线 4：章级 story-system 刷新必须同时 --persist 与 --emit-runtime-contracts。"""
    text = _read_text(SKILLS_DIR / skill_name / "SKILL.md")
    cmd_start = text.find('story-system "${CHAPTER_GOAL}"')
    assert cmd_start >= 0, f"{skill_name}: 缺少章级 story-system 调用"
    # 取该调用所在的命令行（到下一空行/段落结束），断言两个关键开关都在
    cmd_tail = text[cmd_start:cmd_start + 400]
    assert "--persist" in cmd_tail, f"{skill_name}: 章级 story-system 缺少 --persist"
    assert "--emit-runtime-contracts" in cmd_tail, (
        f"{skill_name}: 章级 story-system 缺少 --emit-runtime-contracts"
    )
    assert "--chapter" in cmd_tail, f"{skill_name}: 章级 story-system 缺少 --chapter"


# A 类红线 5：write-gate 三道闸门必须齐全且顺序为 prewrite→precommit→postcommit。
def test_write_skill_gate_stages_ordered_prewrite_precommit_postcommit():
    """红线 5：write-gate 三道 gate 顺序不可乱。"""
    text = _read_text(SKILLS_DIR / "webnovel-write" / "SKILL.md")
    prewrite = text.find("write-gate --chapter {chapter_num} --stage prewrite")
    precommit = text.find("write-gate --chapter {chapter_num} --stage precommit")
    postcommit = text.find("write-gate --chapter {chapter_num} --stage postcommit")
    assert prewrite >= 0, "缺少 prewrite gate"
    assert precommit >= 0, "缺少 precommit gate"
    assert postcommit >= 0, "缺少 postcommit gate"
    assert prewrite < precommit < postcommit, (
        "write-gate 三道 gate 顺序必须为 prewrite→precommit→postcommit"
    )


# A 类红线 7：reviewer 原始 JSON 必须经 review-pipeline --save-metrics 落库（write 与 review 两层）。
@pytest.mark.parametrize("skill_name", ["webnovel-write", "webnovel-review"])
def test_review_pipeline_persists_metrics_in_review_chain(skill_name: str):
    """红线 7：reviewer JSON 经 review-pipeline --save-metrics 落库。"""
    text = _read_text(SKILLS_DIR / skill_name / "SKILL.md")
    cmds = _extract_cli_subcommands(text)
    assert "review-pipeline" in cmds, f"{skill_name}: 缺少 review-pipeline CLI 调用"
    assert "--save-metrics" in text, f"{skill_name}: review-pipeline 未带 --save-metrics 落库"


# A 类红线 10：postcommit 必须验证 projection 五项；失败只 projections retry。
def test_write_skill_postcommit_verifies_five_projections_and_retry_only():
    """红线 10：projection 五项（state/index/summary/memory/vector）验证，失败只 retry。"""
    text = _read_text(SKILLS_DIR / "webnovel-write" / "SKILL.md")
    assert "state/index/summary/memory/vector" in text, (
        "缺少 projection 五项（state/index/summary/memory/vector）验证说明"
    )
    # 失败兜底唯一手段是 projections retry（命令以续行书写，直接断言字面调用）
    assert "projections retry --chapter {chapter_num}" in text, (
        "projection 失败兜底必须是 projections retry --chapter {chapter_num}"
    )


# A 类红线 12：plan 必须覆盖节拍表/时间线/结构化章纲节点/结构化总纲写回/状态更新。
def test_plan_skill_covers_outline_writeback_and_state_sync_contract():
    """红线 12：plan 的节拍表/时间线/章纲节点/总纲写回 JSON/master-outline-sync/update-state。"""
    text = _read_text(SKILLS_DIR / "webnovel-plan" / "SKILL.md")
    # 节拍表 / 时间线 输出物
    assert "大纲/第{volume_id}卷-节拍表.md" in text
    assert "大纲/第{volume_id}卷-时间线.md" in text
    # 结构化章纲节点
    for node in ("CBN", "CPNs", "CEN", "必须覆盖节点", "本章禁区"):
        assert node in text, f"plan 缺少结构化章纲节点标记 {node}"
    # 结构化总纲写回文件（不可从自由文本推断伏笔）
    assert "大纲/第{volume_id}卷-总纲写回.json" in text
    # 设定写回 + 状态同步命令
    cmds = _extract_cli_subcommands(text)
    assert "master-outline-sync" in cmds, "plan 缺少 master-outline-sync 写回命令"
    assert "update-state" in cmds, "plan 缺少 update-state 状态更新命令"


# ---------------------------------------------------------------------------
# 8. B 类跨层新契约（plan §5.2-B / §4.5 写入所有权矩阵）
#    tools↔落盘一致性现状已满足 → 作通过型守护；
#    提交前只读 git diff 变更面校验现状缺失 → xfail，Task 5（Phase 1）落地后移除标记转正。
# ---------------------------------------------------------------------------

# _agent_tools removed in v1.0.19 — agents migrated to dispatch_task("file-agent")


# B 类红线（写入所有权 ↔ tools 一致，单一写入者）：
# data-agent 是三份 tmp artifact 的唯一写入者 → 必须持 Write；
# reviewer/context-agent/deconstruction-agent 只返回结果、由主流程落盘 → 不得持 Write。

def test_write_skill_has_readonly_git_diff_change_surface_check():
    """红线（提交前变更面校验）：write SKILL 在 chapter-commit 前执行只读 git diff 校验。"""
    text = _read_text(SKILLS_DIR / "webnovel-write" / "SKILL.md")
    assert "diff --name-status" in text, (
        "write SKILL 缺少提交前只读 git diff --name-status 变更面校验"
    )
    assert "diff --check" in text, (
        "write SKILL 缺少 git diff --check 空白/冲突标记校验"
    )


# B 类红线（写入所有权·prompt 层）：write/review 必须在文本层声明所有权，
# 与 frontmatter（test_agent_write_ownership_matches_tools_frontmatter）+ behavior eval（artifact_ownership）三处互守。
def test_write_review_skills_state_artifact_ownership():
    """reviewer 返回 JSON、主流程落盘 review_results.json、data-agent 唯一写入者。"""
    write_text = _read_text(SKILLS_DIR / "webnovel-write" / "SKILL.md")
    review_text = _read_text(SKILLS_DIR / "webnovel-review" / "SKILL.md")
    for name, text in (("webnovel-write", write_text), ("webnovel-review", review_text)):
        assert "主流程" in text and ".webnovel/tmp/review_results.json" in text, (
            f"{name}: 缺 reviewer→主流程落盘 review_results.json 的所有权说明"
        )
    assert "唯一写入者" in write_text, "webnovel-write 缺 file-agent 唯一写入者说明"
    assert "主流程只检查文件存在与 schema" in write_text
    assert "不直接写 state/index/summaries/memory/vectors/projection" in write_text


# §9.3/§12.3 审查阈值测试已在 webnovel-review SKILL.md 中由 dispatch_task("file-agent") 覆盖。
# test_reviewer_has_no_react_meta_narrative 随 agents/ 目录删除一并移除（v1.0.19）。
