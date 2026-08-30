"""项目级风格提示词提炼服务。

同一个项目（剧本）的艺术风格提示词与导演叙事提示词，在分镜脚本生成前
用项目文本模型从绑定的风格/导演手册中统一提炼一次，并固定到项目字段
art_style_prompt / director_style_prompt，供分镜脚本、分镜图等后续生成
操作直接引用；项目重新绑定风格或导演手册时由项目更新服务清空对应字段，
下次生成前重新提炼固定。
"""

import re
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import project_path, settings
from app.models.project import Project
from app.services.agent_gateway import ProviderModelGateway
from app.services.prompt_registry import PromptRegistry, PromptRegistryError
from app.utils.time_tools import utc_now


# 风格键仅允许目录名安全字符，防止路径逃逸。
_SKILL_PATH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")

# 提炼输入的手册正文上限：手册全文进文本模型，超出部分截断。
_DISTILL_CONTEXT_MAX_CHARS = 10000

# data/skills 提示词文件缺失时的内置回退模板，与技能文件保持同等约束。
_FALLBACK_ART_STYLE_DISTILL_PROMPT = (
    "你是一位资深美术指导。阅读给定的艺术风格手册正文，把它提炼为一段可直接注入"
    "文生图提示词的美术风格提示词。\n\n"
    "只保留可执行的视觉规范：媒介与画种、线条与笔触、上色方式、光影处理、"
    "色彩与调色倾向、材质质感、画面质量要求。\n"
    "忽略目录、流程、管理、命名、素材组织等非视觉内容；"
    "不要包含剧情、角色姓名或具体场景内容。\n\n"
    "输出 150-300 字的简体中文连贯段落，只输出提示词正文，不要任何解释、标题或列表符号。"
)
_FALLBACK_DIRECTOR_STYLE_DISTILL_PROMPT = (
    "你是一位资深导演。阅读给定的导演风格手册正文，把它提炼为一段指导分镜与画面"
    "叙事的叙事提示词。\n\n"
    "只保留可执行的叙事规范：景别与机位偏好、运镜方式、构图倾向、叙事节奏与停顿、"
    "情绪与表演处理、转场与信息释放方式。\n"
    "忽略目录、流程、管理等非叙事内容；不要包含美术外观描述、具体剧情或角色姓名。\n\n"
    "输出 150-300 字的简体中文连贯段落，只输出提示词正文，不要任何解释、标题或列表符号。"
)


def load_art_style_distill_prompt(registry: PromptRegistry | None = None) -> str:
    """从 data/skills 读取艺术风格提炼提示词模板，缺失时回退内置模板。"""

    prompt_name = settings.art_style_distill_prompt_name.strip()
    if not prompt_name:
        return _FALLBACK_ART_STYLE_DISTILL_PROMPT
    prompt_registry = registry or PromptRegistry.from_settings()
    try:
        return prompt_registry.skill(prompt_name)
    except PromptRegistryError:
        return _FALLBACK_ART_STYLE_DISTILL_PROMPT


def load_director_style_distill_prompt(registry: PromptRegistry | None = None) -> str:
    """从 data/skills 读取导演叙事提炼提示词模板，缺失时回退内置模板。"""

    prompt_name = settings.director_style_distill_prompt_name.strip()
    if not prompt_name:
        return _FALLBACK_DIRECTOR_STYLE_DISTILL_PROMPT
    prompt_registry = registry or PromptRegistry.from_settings()
    try:
        return prompt_registry.skill(prompt_name)
    except PromptRegistryError:
        return _FALLBACK_DIRECTOR_STYLE_DISTILL_PROMPT


def load_style_context(style_key: str, configured_root: str, max_chars: int) -> str:
    """按风格键读取风格/导演手册目录下全部 Markdown 正文，超限截断。"""

    key = style_key.strip()
    if not key or not _SKILL_PATH_PATTERN.fullmatch(key):
        return ""
    root = project_path(configured_root)
    style_dir = (root / key).resolve()
    try:
        style_dir.relative_to(root)
    except ValueError:
        return ""
    if not style_dir.is_dir():
        return ""
    parts: list[str] = []
    for path in sorted(style_dir.rglob("*.md")):
        if not path.is_file():
            continue
        relative = path.relative_to(style_dir).as_posix()
        content = path.read_text(encoding="utf-8", errors="ignore").strip()
        if content:
            parts.append(f"### {relative}\n{content}")
        if len("\n\n".join(parts)) >= max_chars:
            break
    return "\n\n".join(parts)[:max_chars]


def build_style_prompt_gateway() -> ProviderModelGateway:
    return ProviderModelGateway(timeout=settings.model_request_timeout_seconds)


async def _distill(
    gateway: Any,
    *,
    model_id: str,
    system_prompt: str,
    style_key: str,
    manual: str,
) -> str:
    """调用文本模型把手册正文提炼为提示词段落。"""

    text = await gateway.generate_text(
        model_id=model_id,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"styleKey: {style_key}\n\n## 手册正文\n{manual}"},
        ],
    )
    return str(text or "").strip()


async def ensure_project_style_prompts(
    session: AsyncSession,
    project: Project,
    *,
    model_id: str = "",
    gateway: Any | None = None,
) -> tuple[str, str]:
    """确保项目的风格/叙事提示词已提炼固定，返回 (风格提示词, 叙事提示词)。

    已固定的直接返回（幂等引用）；未固定且项目绑定了手册与文本模型时提炼并
    落库固定。绑定为空或无可用文本模型时返回现状，不视为错误。
    """

    resolved_model_id = (model_id or project.text_model or "").strip()
    art_style_prompt = (project.art_style_prompt or "").strip()
    director_style_prompt = (project.director_style_prompt or "").strip()
    updated = False

    art_style_key = str(project.art_style or "").strip()
    if not art_style_prompt and art_style_key and resolved_model_id:
        manual = load_style_context(art_style_key, settings.visual_style_root, _DISTILL_CONTEXT_MAX_CHARS)
        if manual:
            resolved_gateway = gateway or build_style_prompt_gateway()
            gateway = resolved_gateway
            art_style_prompt = await _distill(
                resolved_gateway,
                model_id=resolved_model_id,
                system_prompt=load_art_style_distill_prompt(),
                style_key=art_style_key,
                manual=manual,
            )
            project.art_style_prompt = art_style_prompt
            updated = True

    director_style_key = str(project.director_manual or "").strip()
    if not director_style_prompt and director_style_key and resolved_model_id:
        manual = load_style_context(director_style_key, settings.director_manual_root, _DISTILL_CONTEXT_MAX_CHARS)
        if manual:
            resolved_gateway = gateway or build_style_prompt_gateway()
            director_style_prompt = await _distill(
                resolved_gateway,
                model_id=resolved_model_id,
                system_prompt=load_director_style_distill_prompt(),
                style_key=director_style_key,
                manual=manual,
            )
            project.director_style_prompt = director_style_prompt
            updated = True

    if updated:
        project.updated_at = utc_now()
        session.add(project)
        await session.flush()
    return art_style_prompt, director_style_prompt