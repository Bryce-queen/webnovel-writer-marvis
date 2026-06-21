#!/usr/bin/env bash
# install-jwynia-deps.sh — 将 jwynia 创作技法技能安装到 Marvis market 目录
#
# webnovel-writer 依赖以下 10 个 jwynia 技能进行创作诊断：
#   story-idea-generator | worldbuilding | genre-conventions | dialogue
#   scene-sequencing | plot-structure | story-sense | prose-style
#   prose-critique | revision
#
# 用法: bash scripts/install-jwynia-deps.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPS_ROOT="$SCRIPT_DIR/../deps/jwynia/skills"

# 查找 Marvis skills/market 目录（多 UUID 子目录下取最新）
MARVIS_BASE="$HOME/Library/Application Support/com.tencent.mac.marvis/MarvisData/User"
if [ ! -d "$MARVIS_BASE" ]; then
    echo "[ERROR] Marvis data directory not found: $MARVIS_BASE"
    echo "Make sure Marvis is installed and has been launched at least once."
    exit 1
fi

# 遍历所有 User 子目录，取 skills/market/ 存在的
TARGET=""
for user_dir in "$MARVIS_BASE"/*/; do
    candidate="${user_dir}skills/market"
    if [ -d "$candidate" ]; then
        TARGET="$candidate"
        break
    fi
done

if [ -z "$TARGET" ]; then
    echo "[ERROR] No skills/market/ directory found under any MarvisData/User/*/"
    exit 1
fi

echo "[INFO] Target market directory: $TARGET"
echo ""

COPIED=0
FAILED=0

for skill_dir in "$DEPS_ROOT"/*/; do
    skill_name=$(basename "$skill_dir")
    src="$skill_dir/SKILL.md"

    if [ ! -f "$src" ]; then
        echo "[SKIP] $skill_name — no SKILL.md found"
        continue
    fi

    dest_dir="$TARGET/$skill_name"
    mkdir -p "$dest_dir"

    if cp "$src" "$dest_dir/SKILL.md"; then
        echo "[ OK ] $skill_name → $dest_dir/SKILL.md"
        COPIED=$((COPIED + 1))
    else
        echo "[FAIL] $skill_name"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "=============================="
echo " Installed: $COPIED  Failed: $FAILED"
echo "=============================="
echo ""
echo "Next: Restart Marvis for the new skills to take effect."
