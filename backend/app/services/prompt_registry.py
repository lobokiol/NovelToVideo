from __future__ import annotations

from pathlib import Path

from app.core.config import (
    Settings,
    skills_root_path,
)


class PromptRegistryError(Exception):
    """提示词技能加载失败。"""


class PromptRegistry:
    """从当前项目的技能目录加载提示词。"""

    def __init__(
        self,
        root: str | Path,
        *,
        prompts: dict[str, str | Path] | None = None,
    ) -> None:
        self._root = Path(root).expanduser().resolve()
        self._prompts = {
            self._normalize_task_type(key): Path(value).expanduser().resolve()
            for key, value in (prompts or {}).items()
        }
        self._cache: dict[str, str] = {}
        self._index: dict[str, Path] | None = None

    @classmethod
    def from_settings(cls, config: Settings | None = None) -> "PromptRegistry":
        return cls(skills_root_path(config))

    def skill(self, task_type: str) -> str:
        key = self._normalize_task_type(task_type)
        if key not in self._cache:
            self._cache[key] = self._load_skill(key)
        return self._cache[key]

    def _load_skill(self, task_type: str) -> str:
        path = self._resolve_skill_path(task_type)
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise PromptRegistryError(f"提示词技能内容为空：{task_type}")
        return content

    def _resolve_skill_path(self, task_type: str) -> Path:
        if task_type in self._prompts:
            return self._validate_prompt_file(
                task_type,
                self._prompts[task_type],
                allow_outside_root=True,
            )

        index = self._skill_index()
        path = index.get(task_type)
        if path is None:
            raise PromptRegistryError(f"提示词技能不存在：{task_type}")
        return self._validate_prompt_file(task_type, path, allow_outside_root=False)

    def _skill_index(self) -> dict[str, Path]:
        if self._index is not None:
            return self._index

        index: dict[str, Path] = {}
        conflicts: set[str] = set()
        if self._root.exists():
            for path in sorted(self._root.rglob("*.md")):
                key = path.parent.name if path.name.lower() == "readme.md" else path.stem
                key = self._normalize_task_type(key)
                if key in index and index[key] != path:
                    conflicts.add(key)
                    continue
                index[key] = path.resolve()

        for key in conflicts:
            index.pop(key, None)
        self._index = index
        return index

    def _validate_prompt_file(
        self,
        task_type: str,
        path: Path,
        *,
        allow_outside_root: bool,
    ) -> Path:
        path = path.resolve()
        if not allow_outside_root:
            try:
                path.relative_to(self._root)
            except ValueError as exc:
                raise PromptRegistryError(f"提示词技能路径越过根目录：{task_type}") from exc
        if not path.is_file():
            raise PromptRegistryError(f"提示词技能不存在：{task_type}")
        if path.suffix.lower() != ".md":
            raise PromptRegistryError(f"提示词技能必须是 Markdown 文件：{task_type}")
        return path

    @staticmethod
    def _normalize_task_type(task_type: str) -> str:
        key = (task_type or "").strip()
        if not key:
            raise PromptRegistryError("提示词技能名称不能为空")
        if any(char in key for char in ("/", "\\", "..")):
            raise PromptRegistryError(f"提示词技能名称不合法：{task_type}")
        return key
