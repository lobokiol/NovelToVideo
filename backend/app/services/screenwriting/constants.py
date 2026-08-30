"""剧本创作流程共享常量。

阶段定义、工作流状态键、阶段技能映射与剧本质量阈值集中于此。
本模块不依赖包内其他子模块，避免循环导入。
"""

from __future__ import annotations


STAGE_ORDER: tuple[str, ...] = ("skeleton", "strategy", "script")
STAGE_PREREQUISITES: dict[str, tuple[str, ...]] = {
    "skeleton": (),
    "strategy": ("skeleton",),
    "script": ("skeleton", "strategy"),
}
STAGE_SKILL_PROMPTS: dict[str, str] = {
    "skeleton": "story_skeleton_agent",
    "strategy": "adaptation_strategy_agent",
    "script": "screenplay_generation_agent",
}
CREATION_CONFIG_SKILL_PROMPT = "creation_config_agent"

# 阶段识别关键词：用于判断用户发言指向哪个创作阶段。
STAGE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("skeleton", ("故事骨架", "主线骨架", "骨架", "故事大纲", "主线", "story skeleton", "skeleton")),
    ("strategy", ("改编策略", "策略", "改编方案", "取舍", "基调", "adaptation strategy", "strategy")),
    ("script", ("剧本", "分场", "场景", "对白", "台词", "screenplay", "script")),
)
GENERATION_KEYWORDS: tuple[str, ...] = (
    "生成",
    "梳理",
    "制定",
    "提出",
    "开始",
    "创作",
    "输出",
    "写",
    "补",
    "补强",
    "打磨",
    "整理",
    "generate",
    "create",
    "draft",
    "write",
)

# 工作流状态键（持久化在会话 workflow JSON 中）。
WORKFLOW_PROJECT_CONFIG = "projectConfig"
WORKFLOW_BASIC_INFO_CONFIRMED = "basicInfoConfirmed"
WORKFLOW_PENDING_STAGE = "pendingStage"
WORKFLOW_PENDING_STAGE_MESSAGE = "pendingStageMessage"
WORKFLOW_PENDING_CONFIG_CHANGE = "pendingConfigChange"
WORKFLOW_COMPLETED_STAGE = "completedStage"
WORKFLOW_STAGE_SOURCE = "stageSource"
WORKFLOW_PENDING_SCRIPT_REPAIR = "pendingScriptTruncationRepair"
WORKFLOW_STAGE_ASSESSMENTS = "stageAssessments"

# 故事骨架模板化占位词黑名单：出现即判定为未绑定具体事件的模板输出。
TEMPLATE_SKELETON_MARKERS: tuple[str, ...] = (
    "主角的核心目标",
    "现实压力/情感牵引/任务驱动",
    "主要对立者/阻碍者",
    "关键支持者",
    "潜在隐藏人物/信息源",
    "某一核心事件",
    "个人选择",
    "外部压力",
    "介绍主角与基本处境",
    "抛出故事起点事件/异常事件",
    "本故事以主角卷入",
)

# 阶段提示词单段上下文上限与剧本质量阈值（阶段 4 质量护栏使用）。
STAGE_PROMPT_SECTION_MAX_CHARS = 20000
STAGE_SELF_REPAIR_MAX_ATTEMPTS = 2
SCRIPT_SCENE_MIN_DIALOGUE_LINES = 6
SCRIPT_SCENE_MIN_DIALOGUE_CHARS = 220
SCRIPT_SCENE_MIN_ACTION_LINES = 4
SCRIPT_EPISODE_DURATION_MIN_RATIO = 0.8
SCRIPT_EPISODE_DURATION_MAX_RATIO = 1.2