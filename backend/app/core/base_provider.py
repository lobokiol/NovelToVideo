from __future__ import annotations

import ast
from pprint import pformat
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import BASE_DIR, settings
from app.schemas.provider import ProviderConfig, ProviderModel
from app.utils.secret_tools import decrypt_secret, encrypt_secret

PROVIDERS_DIR = Path(__file__).resolve().parents[1] / "providers"
_CONFIGURED_PROVIDER_TEMPLATE_PATH = Path(settings.provider_template_path).expanduser()
PROVIDER_TEMPLATE_PATH = (
    _CONFIGURED_PROVIDER_TEMPLATE_PATH
    if _CONFIGURED_PROVIDER_TEMPLATE_PATH.is_absolute()
    else BASE_DIR / _CONFIGURED_PROVIDER_TEMPLATE_PATH
).resolve()
PROVIDER_CONFIG_NAME = "PROVIDER_CONFIG"
PROVIDER_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_PROVIDER_FILE_LOCK = threading.RLock()
_FALLBACK_SECRET_KEYS = {"apikey", "api_key", "token", "secret", "password"}

class ProviderServiceError(Exception):
    """服务配置管理基础异常。"""


class ProviderNotFoundError(ProviderServiceError):
    """服务文件不存在。"""


class ProviderConflictError(ProviderServiceError):
    """服务文件已存在。"""


class ProviderValidationError(ProviderServiceError):
    """服务文件或 PROVIDER_CONFIG 配置不合法。"""


class ProviderRemoteRequestError(ProviderServiceError):
    """请求远端大模型服务失败。"""


class ProviderConfigurationError(ProviderServiceError):
    """Provider 运行配置不完整。"""


class BaseProvider:
    """Provider 运行时基类。"""

    provider_key = ""
    provider_config: dict[str, Any] = {}
    model_type = ""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        input_values: dict[str, str] | None = None,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        config_input_values = self.provider_config.get("input_values") or {}
        self.input_values = {**config_input_values, **(input_values or {})}
        self.api_key = api_key
        self.base_url = base_url or str(self.provider_config.get("base_url") or "")
        self.timeout = timeout
        self.client = client

    async def generate(self, *, model_id: str | None = None, **kwargs: Any) -> Any:
        """执行生成任务。"""
        raise NotImplementedError("请在具体 Provider 中实现生成逻辑")


def list_provider_configs(root: Path | None = None) -> list[ProviderConfig]:
    """在不导入模块的情况下读取所有服务文件配置。"""
    providers_root = _resolve_providers_root(root)
    if not providers_root.exists():
        return []

    configs = [
        _read_provider_config_from_file(path)
        for path in sorted(providers_root.glob("*.py"))
        if _is_service_file(path)
    ]
    return sorted(configs, key=lambda item: (item.sort_order, item.key))


def get_provider_config(key: str, root: Path | None = None) -> ProviderConfig:
    """按服务唯一标记读取配置。"""
    return _read_provider_config_from_file(_provider_file(key, root))


def get_provider_code(key: str, root: Path | None = None) -> str:
    """按服务唯一标记读取源码。"""
    return _provider_file(key, root).read_text(encoding="utf-8")


def get_provider_code_for_response(key: str, root: Path | None = None) -> str:
    """读取服务源码，并将 PROVIDER_CONFIG 中的敏感输入值加密后返回。"""
    provider_file = _provider_file(key, root)
    source = provider_file.read_text(encoding="utf-8")
    config = _encrypt_sensitive_input_values(_read_provider_config_from_source(source, provider_file))
    return _replace_provider_config_in_source(source, provider_file, config)


def prepare_provider_config_for_response(config: ProviderConfig | dict[str, Any]) -> ProviderConfig:
    """返回给客户端前加密 password 类型输入值，避免泄露明文密钥。"""
    return _encrypt_sensitive_input_values(_validate_config(config))


def update_provider_config(
    key: str,
    config: ProviderConfig | dict[str, Any],
    root: Path | None = None,
) -> ProviderConfig:
    """替换已有服务文件中的 PROVIDER_CONFIG 字面量。"""
    parsed_config = _encrypt_sensitive_input_values(_validate_config(config))
    _ensure_key_matches(key, parsed_config)
    with _PROVIDER_FILE_LOCK:
        provider_file = _provider_file(key, root)
        source = provider_file.read_text(encoding="utf-8")
        updated_source = _replace_provider_config_in_source(source, provider_file, parsed_config)
        _validate_python_source(updated_source, provider_file)
        _write_provider_file_atomic(provider_file, updated_source, backup=True)
    return parsed_config

def update_provider_input_values(
    key: str,
    input_values: dict[str, str],
    root: Path | None = None,
) -> ProviderConfig:
    """只更新 PROVIDER_CONFIG 中的 input_values。"""
    current = get_provider_config(key, root)
    updated = current.model_copy(update={"input_values": input_values})
    return update_provider_config(key, updated, root)


def create_provider_file(
    config: ProviderConfig | dict[str, Any],
    root: Path | None = None,
    code: str | None = None,
) -> ProviderConfig:
    """根据配置和可选源码创建新的服务文件。"""
    parsed_config = _encrypt_sensitive_input_values(_validate_config(config))
    with _PROVIDER_FILE_LOCK:
        providers_root = _resolve_providers_root(root)
        providers_root.mkdir(parents=True, exist_ok=True)
        provider_file = _provider_file(parsed_config.key, providers_root, must_exist=False)
        if provider_file.exists():
            raise ProviderConflictError("服务文件已存在")

        if code is None:
            source = build_provider_template(parsed_config)
        else:
            source = code
            _read_provider_config_from_source(source, provider_file)
            source = _replace_provider_config_in_source(source, provider_file, parsed_config)
        _validate_provider_source(source, provider_file, require_provider_class=True)
        _write_provider_file_atomic(provider_file, source, backup=False)
        return parsed_config

def update_provider_code(
    key: str,
    code: str,
    root: Path | None = None,
) -> ProviderConfig:
    """校验 PROVIDER_CONFIG 后替换已有服务文件源码。"""
    with _PROVIDER_FILE_LOCK:
        provider_file = _provider_file(key, root)
        config = _encrypt_sensitive_input_values(_read_provider_config_from_source(code, provider_file))
        _ensure_key_matches(key, config)
        source = _replace_provider_config_in_source(code, provider_file, config)
        _validate_provider_source(source, provider_file, require_provider_class=True)
        _write_provider_file_atomic(provider_file, source, backup=True)
    return config


def delete_provider_file(key: str, root: Path | None = None) -> None:
    """备份后删除已有服务文件。"""
    with _PROVIDER_FILE_LOCK:
        provider_file = _provider_file(key, root)
        _backup_provider_file(provider_file)
        provider_file.unlink()


def build_provider_template(config: ProviderConfig | dict[str, Any] | None = None) -> str:
    """生成基础大模型工具类模板。"""
    template_source = _read_provider_template_source(PROVIDER_TEMPLATE_PATH)
    parsed_config = (
        _encrypt_sensitive_input_values(_read_provider_config_from_source(template_source, PROVIDER_TEMPLATE_PATH))
        if config is None
        else _encrypt_sensitive_input_values(_validate_config(config))
    )
    return _replace_provider_config_in_source(template_source, PROVIDER_TEMPLATE_PATH, parsed_config)


async def fetch_provider_models(
    config: ProviderConfig | dict[str, Any],
    *,
    timeout: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> list[ProviderModel]:
    """使用当前表单配置临时请求远端 /models，并转换为项目模型元数据。"""
    parsed_config = _validate_config(config)
    builtin_models = _builtin_provider_models(parsed_config)
    if builtin_models is not None:
        return builtin_models

    models_url = _build_models_url(_resolve_models_base_url(parsed_config))
    api_key = _resolve_models_api_key(parsed_config)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        if client is not None:
            response = await client.get(models_url, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=timeout) as owned_client:
                response = await owned_client.get(models_url, headers=headers)
    except httpx.HTTPError as exc:
        raise ProviderRemoteRequestError(f"模型列表获取失败: {exc}") from exc

    if response.status_code >= 400:
        raise ProviderRemoteRequestError(
            f"模型列表获取失败，HTTP {response.status_code}: {response.text}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderRemoteRequestError("模型列表响应不是合法 JSON") from exc
    return _normalize_remote_models(payload)


def _builtin_provider_models(config: ProviderConfig) -> list[ProviderModel] | None:
    provider_marker = {config.key.lower(), config.protocol.lower()}
    return provider_marker

def _replace_provider_config_in_source(source: str, path: Path, config: ProviderConfig) -> str:
    node = _find_provider_config_node(source, path)
    if node.end_lineno is None:
        raise ProviderValidationError("无法定位 PROVIDER_CONFIG 结束行")
    lines = source.splitlines(keepends=True)
    replacement = f"{PROVIDER_CONFIG_NAME} = {_format_python_literal(config)}\n"
    return "".join(lines[: node.lineno - 1]) + replacement + "".join(lines[node.end_lineno :])


def _validate_provider_source(source: str, path: Path, *, require_provider_class: bool = False) -> None:
    _validate_python_source(source, path)
    if require_provider_class and not _has_base_provider_subclass(source, path):
        raise ProviderValidationError("服务文件必须至少声明一个继承 BaseProvider 的工具类")


def _validate_python_source(source: str, path: Path) -> None:
    try:
        compile(source, str(path), "exec")
    except SyntaxError as exc:
        raise ProviderValidationError(f"{path.name} 不是合法 Python 源码: {exc.msg}") from exc


def _has_base_provider_subclass(source: str, path: Path) -> bool:
    try:
        module = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ProviderValidationError(f"{path.name} 不是合法 Python 源码: {exc.msg}") from exc
    for node in module.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if any(_base_name(base) == "BaseProvider" for base in node.bases):
            return True
    return False


def _base_name(base: ast.expr) -> str:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    if isinstance(base, ast.Subscript):
        return _base_name(base.value)
    return ""


def _encrypt_sensitive_input_values(config: ProviderConfig) -> ProviderConfig:
    if not config.input_values:
        return config
    values = dict(config.input_values)
    for key in _sensitive_input_keys(config):
        if values.get(key):
            values[key] = encrypt_secret(values[key])
    return config.model_copy(update={"input_values": values})


def _sensitive_input_keys(config: ProviderConfig) -> set[str]:
    keys = {item.key for item in config.inputs if item.type == "password"}
    for key in config.input_values:
        if key.lower() in _FALLBACK_SECRET_KEYS:
            keys.add(key)
    return keys


def _resolve_models_base_url(config: ProviderConfig) -> str:
    values = config.input_values or {}
    candidates = [
        values.get("baseUrl"),
        values.get("base_url"),
        values.get("OPEN_BASE_URL"),
        values.get("OPENAI_BASE_URL"),
        values.get("BASE_URL"),
    ]
    candidates.extend(values.get(item.key) for item in config.inputs if item.type == "url")
    candidates.append(config.base_url)

    for value in candidates:
        base_url = str(value or "").strip()
        if base_url:
            return base_url
    raise ProviderValidationError("缺少请求地址")


def _build_models_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized.startswith(("http://", "https://")):
        raise ProviderValidationError("请求地址必须以 http:// 或 https:// 开头")
    if normalized.endswith("/models"):
        return normalized
    return f"{normalized}/models"


def _resolve_models_api_key(config: ProviderConfig) -> str:
    values = config.input_values or {}
    candidates = [
        values.get("apiKey"),
        values.get("api_key"),
        values.get("OPENAI_API_KEY"),
        values.get("API_KEY"),
        values.get("token"),
    ]
    candidates.extend(values.get(item.key) for item in config.inputs if item.type == "password")
    candidates.extend(
        value
        for key, value in values.items()
        if key.lower().endswith(("api_key", "apikey", "token"))
    )

    for value in candidates:
        raw_value = str(value or "").strip()
        if not raw_value:
            continue
        try:
            api_key = decrypt_secret(raw_value).strip()
        except ValueError as exc:
            raise ProviderValidationError("API Key 解密失败") from exc
        if api_key.lower().startswith("bearer "):
            api_key = api_key[7:].strip()
        if api_key:
            return api_key
    raise ProviderValidationError("缺少 API Key")


def _normalize_remote_models(payload: Any) -> list[ProviderModel]:
    if isinstance(payload, dict):
        raw_items = payload.get("data") or payload.get("models") or payload.get("items") or []
    elif isinstance(payload, list):
        raw_items = payload
    else:
        raise ProviderRemoteRequestError("模型列表响应格式不合法")

    if not isinstance(raw_items, list):
        raise ProviderRemoteRequestError("模型列表响应格式不合法")

    models: list[ProviderModel] = []
    seen: set[str] = set()
    for item in raw_items:
        model_id = _remote_model_id(item)
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        model_type = _infer_model_type(model_id)
        models.append(
            ProviderModel(
                name=_remote_model_name(item, model_id),
                model_id=model_id,
                model_type=model_type,
                description=_remote_model_description(item),
                modes=["text"],
                think=False,
                voices=[],
                audio=None,
                duration_resolution_map=[],
                raw_config=item if isinstance(item, dict) else {"id": model_id},
            )
        )
    return models


def _remote_model_id(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    value = item.get("id") or item.get("model_id") or item.get("modelId") or item.get("name")
    return str(value or "").strip()


def _remote_model_name(item: Any, model_id: str) -> str:
    if isinstance(item, dict):
        value = item.get("display_name") or item.get("displayName") or item.get("name")
        if value:
            return str(value).strip()
    return model_id


def _remote_model_description(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    value = item.get("description") or item.get("owned_by") or item.get("owner") or ""
    return str(value).strip()


def _infer_model_type(model_id: str) -> str:
    lowered = model_id.lower()
    if any(marker in lowered for marker in ("sora", "video", "veo", "seedance")):
        return "video"
    if any(marker in lowered for marker in ("image", "dall-e", "seedream")):
        return "image"
    if any(marker in lowered for marker in ("tts", "speech", "audio")):
        return "tts"
    return "text"


def _write_provider_file_atomic(path: Path, source: str, *, backup: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        if backup and path.exists():
            _backup_provider_file(path)
        temp_path.write_text(source, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _backup_provider_file(path: Path) -> Path:
    if not path.exists():
        raise ProviderNotFoundError("服务文件不存在")
    timestamp = time.strftime("%Y%m%d%H%M%S")
    backup_path = path.with_name(f"{path.name}.{timestamp}.{uuid4().hex[:8]}.bak")
    backup_source = _encrypted_provider_source_for_backup(path)
    if backup_source is None:
        shutil.copy2(path, backup_path)
        return backup_path
    backup_path.write_text(backup_source, encoding="utf-8")
    return backup_path


def _encrypted_provider_source_for_backup(path: Path) -> str | None:
    source = path.read_text(encoding="utf-8")
    try:
        config = _encrypt_sensitive_input_values(_read_provider_config_from_source(source, path))
        return _replace_provider_config_in_source(source, path, config)
    except ProviderServiceError:
        return None


def _read_provider_config_from_file(path: Path) -> ProviderConfig:
    if not path.exists() or not path.is_file():
        raise ProviderNotFoundError("服务文件不存在")
    return _read_provider_config_from_source(path.read_text(encoding="utf-8"), path)


def _read_provider_template_source(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise ProviderValidationError("服务模板文件不存在")
    source = path.read_text(encoding="utf-8")
    _validate_provider_source(source, path, require_provider_class=True)
    return source


def _read_provider_config_from_source(source: str, path: Path) -> ProviderConfig:
    node = _find_provider_config_node(source, path)
    try:
        value = ast.literal_eval(node.value)
    except (ValueError, SyntaxError) as exc:
        raise ProviderValidationError(f"{path.name} 中的 PROVIDER_CONFIG 必须是字面量字典") from exc
    if not isinstance(value, dict):
        raise ProviderValidationError(f"{path.name} 中的 PROVIDER_CONFIG 必须是字典")
    return _validate_config(value)


def _find_provider_config_node(source: str, path: Path) -> ast.Assign | ast.AnnAssign:
    try:
        module = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ProviderValidationError(f"{path.name} 不是合法 Python 源码: {exc.msg}") from exc

    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == PROVIDER_CONFIG_NAME:
                    return node
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == PROVIDER_CONFIG_NAME:
                return node
    raise ProviderValidationError(f"{path.name} 未声明 PROVIDER_CONFIG")


def _validate_config(config: ProviderConfig | dict[str, Any]) -> ProviderConfig:
    if isinstance(config, ProviderConfig):
        return config
    try:
        return ProviderConfig.model_validate(config)
    except Exception as exc:
        raise ProviderValidationError(str(exc)) from exc


def _format_python_literal(config: ProviderConfig) -> str:
    data = config.model_dump(mode="json", by_alias=False)
    return pformat(data, width=100, sort_dicts=False)


def _provider_file(
    key: str,
    root: Path | None = None,
    *,
    must_exist: bool = True,
) -> Path:
    _validate_provider_key(key)
    providers_root = _resolve_providers_root(root)
    provider_file = (providers_root / f"{key}.py").resolve()
    _ensure_path_inside(provider_file, providers_root)
    if must_exist and not provider_file.exists():
        raise ProviderNotFoundError("服务文件不存在")
    return provider_file


def _resolve_providers_root(root: Path | None = None) -> Path:
    return (root or PROVIDERS_DIR).resolve()


def _ensure_path_inside(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ProviderValidationError("服务文件路径不能逃逸 providers 根目录") from exc


def _validate_provider_key(key: str) -> None:
    if not PROVIDER_KEY_PATTERN.fullmatch(key):
        raise ProviderValidationError("服务唯一标记只能使用小写字母、数字和下划线，且必须以字母开头")


def _ensure_key_matches(expected_key: str, config: ProviderConfig) -> None:
    if config.key != expected_key:
        raise ProviderValidationError("PROVIDER_CONFIG.key 必须与服务文件名一致")


def _is_service_file(path: Path) -> bool:
    return path.name != "__init__.py" and not path.name.startswith("_")
