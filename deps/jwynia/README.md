# Jwynia 技法技能依赖

webnovel-writer 在创作管线中依赖以下 10 个 jwynia 创作技法技能。

## 包含的技能

| 技能 | 文件 | 用途 |
|------|------|------|
| story-idea-generator | [skills/story-idea-generator/SKILL.md](skills/story-idea-generator/SKILL.md) | 故事核创意发散、金手指差异化 |
| worldbuilding | [skills/worldbuilding/SKILL.md](skills/worldbuilding/SKILL.md) | 世界观厚度与一致性诊断 |
| genre-conventions | [skills/genre-conventions/SKILL.md](skills/genre-conventions/SKILL.md) | 题材类型惯例校验 |
| dialogue | [skills/dialogue/SKILL.md](skills/dialogue/SKILL.md) | 对话调性、角色声音一致性诊断 |
| scene-sequencing | [skills/scene-sequencing/SKILL.md](skills/scene-sequencing/SKILL.md) | 场景-续篇节奏诊断 |
| plot-structure | [skills/plot-structure/SKILL.md](skills/plot-structure/SKILL.md) | 剧情弧线结构诊断 |
| story-sense | [skills/story-sense/SKILL.md](skills/story-sense/SKILL.md) | 叙事健康度三维诊断 |
| prose-style | [skills/prose-style/SKILL.md](skills/prose-style/SKILL.md) | 文笔句子层面诊断 |
| prose-critique | [skills/prose-critique/SKILL.md](skills/prose-critique/SKILL.md) | 对抗性阅读 |
| revision | [skills/revision/SKILL.md](skills/revision/SKILL.md) | 修改策略与连锁影响分析 |

## 安装

存放于本目录仅为分发用途。安装到 Marvis 需要将各 `skills/{skill-name}/SKILL.md` 复制到 Marvis 的 `skills/market/{skill-name}/` 目录。

自动安装：

```bash
bash ../scripts/install-jwynia-deps.sh
```

手动安装：

```bash
for skill in dialogue genre-conventions plot-structure prose-critique prose-style revision scene-sequencing story-idea-generator story-sense worldbuilding; do
  mkdir -p "$MARVIS_MARKET/$skill"
  cp skills/$skill/SKILL.md "$MARVIS_MARKET/$skill/"
done
```

重启 Marvis 后生效。
