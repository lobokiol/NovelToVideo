"""
1. 主体增删查（固定查找：id, email，模糊查找：name）改
2. 关系的增删查改
"""
from __future__ import annotations

import base64
import binascii
import re
import shutil
from pathlib import Path
from urllib.parse import quote


from sqlalchemy import exists, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import BASE_DIR, settings
from app.models.project import Project, ProjectMember, ProjectMemberRole
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectMemberRead, ProjectUpdate
from app.utils.time_tools import utc_now
from app.schemas.project import (
    DirectorManualFileRead,
    DirectorManualFileWrite,
    DirectorManualImageRead,
    DirectorManualImageWrite,
    DirectorManualRead,
    ProjectCreate,
    ProjectUpdate,
    VisualStyleCreate,
    VisualStyleFileRead,
    VisualStyleFileWrite,
    VisualStyleImageRead,
    VisualStyleImageWrite,
    VisualStyleRead,
    VisualStyleUpdate,
    DirectorManualCreate,
)

STYLE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
IMAGES_DIR_NAME = "images"


class ProjectServiceError(Exception):
    """项目服务层基础异常。"""


class ProjectNotFoundError(ProjectServiceError):
    """项目不存在异常。"""


class ProjectAccessDeniedError(ProjectServiceError):
    """当前用户无权访问项目异常。"""


class ProjectMemberNotFoundError(ProjectServiceError):
    """项目成员不存在异常。"""


class ProjectMemberConflictError(ProjectServiceError):
    """项目成员已存在异常。"""

class VisualStyleNotFoundError(ProjectServiceError):
    """视觉风格不存在。"""


class VisualStyleConflictError(ProjectServiceError):
    """视觉风格已存在。"""


class VisualStyleValidationError(ProjectServiceError):
    """视觉风格文件请求不合法。"""


class DirectorManualNotFoundError(ProjectServiceError):
    """导演手册不存在。"""


class DirectorManualConflictError(ProjectServiceError):
    """导演手册已存在。"""


class DirectorManualValidationError(ProjectServiceError):
    """导演手册文件请求不合法。"""


async def get_project_by_id(
    session: AsyncSession,
    project_id: int,
    current_user_public_id: str,
) -> Project | None:
    """按内部主键查询单个项目。"""
    project = await _get_project_by_id(session, project_id)
    if project is None:
        return None
    await _ensure_project_access(session, project, current_user_public_id)
    return project


async def _get_project_by_id(
    session: AsyncSession,
    project_id: int,
) -> Project | None:
    """按内部主键查询单个项目，不做权限过滤。"""
    statement = select(Project).where(Project.id == project_id)
    result = await session.exec(statement)
    return result.first()


async def get_project_by_public_id(
    session: AsyncSession,
    public_id: str,
    current_user_public_id: str,
) -> Project | None:
    """按公开 ID 查询单个项目。"""
    project = await _get_project_by_public_id(session, public_id)
    if project is None:
        return None
    await _ensure_project_access(session, project, current_user_public_id)
    return project


async def _get_project_by_public_id(
    session: AsyncSession,
    public_id: str,
) -> Project | None:
    """按公开 ID 查询单个项目，不做权限过滤。"""
    statement = select(Project).where(Project.public_id == public_id)
    result = await session.exec(statement)
    return result.first()


async def get_project_or_raise(
    session: AsyncSession,
    public_id: str,
    current_user_public_id: str,
) -> Project:
    """按公开 ID 获取项目，不存在时抛出业务异常。"""
    project = await _get_project_by_public_id(session, public_id)
    if project is None:
        raise ProjectNotFoundError("Project not found")
    await _ensure_project_access(session, project, current_user_public_id)
    return project


async def list_projects(session: AsyncSession, current_user_public_id: str) -> list[Project]:
    """获取当前用户可访问的项目列表。"""
    return await _list_accessible_projects(session, current_user_public_id, select(Project))


async def search_projects_by_name(
    session: AsyncSession,
    current_user_public_id: str,
    name: str,
) -> list[Project]:
    """按项目名搜索当前用户可访问的项目列表。"""
    statement = select(Project)
    keyword = name.strip()
    if keyword:
        statement = statement.where(Project.name.ilike(f"%{keyword}%"))
    return await _list_accessible_projects(session, current_user_public_id, statement)


async def search_projects_by_member(
    session: AsyncSession,
    current_user_public_id: str,
    member_public_id: str,
) -> list[Project]:
    """按项目成员搜索当前用户可访问的项目列表。"""
    statement = select(Project).where(
        or_(
            Project.owner_id == member_public_id,
            _project_has_member_condition(member_public_id),
        )
    )
    return await _list_accessible_projects(session, current_user_public_id, statement)


async def search_project_member_candidates(
    session: AsyncSession,
    project_public_id: str,
    keyword: str,
    current_user_public_id: str,
) -> list[User]:
    """按用户名或邮箱搜索可邀请加入项目的用户。"""
    project = await get_project_or_raise(session, project_public_id, current_user_public_id)
    if project.id is None:
        raise ProjectNotFoundError("Project not found")

    search_keyword = keyword.strip()
    if not search_keyword:
        return []

    statement = (
        select(User)
        .where(
            or_(
                User.username.ilike(f"%{search_keyword}%"),
                User.email.ilike(f"%{search_keyword}%"),
            ),
            User.public_id != project.owner_id,
            ~exists().where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_public_id == User.public_id,
            ),
        )
        .order_by(User.sort_order, User.id)
    )
    result = await session.exec(statement)
    return list(result.all())


async def create_project(session: AsyncSession, owner_public_id: str, payload: ProjectCreate) -> Project:
    """创建项目，并自动把创建者加入 owner 成员。"""
    await _get_current_user_or_raise(session, owner_public_id)

    now = utc_now()
    project = Project(
        **payload.model_dump(),
        owner_id=owner_public_id,
        disabled_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(project)
    await session.flush()

    if project.id is None:
        raise ProjectServiceError("Project id was not generated")

    owner_member = ProjectMember(
        project_id=project.id,
        user_public_id=owner_public_id,
        role=ProjectMemberRole.OWNER,
        joined_at=now,
    )
    session.add(owner_member)
    await session.commit()
    await session.refresh(project)
    return project


async def update_project(
    session: AsyncSession,
    public_id: str,
    payload: ProjectUpdate,
    current_user_public_id: str,
) -> Project:
    """更新项目基础信息。"""
    project = await get_project_or_raise(session, public_id, current_user_public_id)

    for field_name in payload.model_fields_set:
        value = getattr(payload, field_name)
        if value is not None:
            setattr(project, field_name, value)

    # 重新绑定风格/导演手册时，清空已固定的提炼提示词，下次生成前重新提炼。
    if "art_style" in payload.model_fields_set and payload.art_style is not None:
        project.art_style_prompt = ""
    if "director_manual" in payload.model_fields_set and payload.director_manual is not None:
        project.director_style_prompt = ""

    project.updated_at = utc_now()
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def disable_project(
    session: AsyncSession,
    public_id: str,
    current_user_public_id: str,
) -> Project:
    """禁用项目。"""
    project = await get_project_or_raise(session, public_id, current_user_public_id)
    await project.disable()
    project.updated_at = utc_now()
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def enable_project(
    session: AsyncSession,
    public_id: str,
    current_user_public_id: str,
) -> Project:
    """启用项目。"""
    project = await get_project_or_raise(session, public_id, current_user_public_id)
    await project.enable()
    project.updated_at = utc_now()
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(
    session: AsyncSession,
    public_id: str,
    current_user_public_id: str,
) -> None:
    """删除项目及其成员关系。"""
    project = await get_project_or_raise(session, public_id, current_user_public_id)
    if project.id is None:
        raise ProjectNotFoundError("Project not found")

    members = await _list_project_members_by_project_id(session, project.id)
    for member in members:
        await session.delete(member)

    await session.delete(project)
    await session.commit()


async def get_project_member(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    current_user_public_id: str,
) -> ProjectMember | None:
    """按项目内部主键和用户公开 ID 查询成员关系。"""
    project = await _get_project_by_id(session, project_id)
    if project is None:
        return None
    await _ensure_project_access(session, project, current_user_public_id)
    return await _get_project_member(session, project_id, user_public_id)


async def _get_project_member(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
) -> ProjectMember | None:
    """按项目内部主键和用户公开 ID 查询成员关系，不做权限过滤。"""
    statement = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_public_id == user_public_id,
    )
    result = await session.exec(statement)
    return result.first()


async def get_project_member_or_raise(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
    current_user_public_id: str,
) -> ProjectMember:
    """获取项目成员，不存在时抛出业务异常。"""
    member = await get_project_member(session, project_id, user_public_id, current_user_public_id)
    if member is None:
        raise ProjectMemberNotFoundError("Project member not found")
    return member


async def list_project_members(
    session: AsyncSession,
    project_public_id: str,
    current_user_public_id: str,
) -> list[ProjectMemberRead]:
    """按项目公开 ID 获取项目成员列表。"""
    project = await get_project_or_raise(session, project_public_id, current_user_public_id)
    if project.id is None:
        raise ProjectNotFoundError("Project not found")
    return await _list_project_member_reads_by_project_id(session, project.id)


async def add_project_member(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    role: ProjectMemberRole,
    current_user_public_id: str,
) -> ProjectMemberRead:
    """新增项目成员。"""
    project = await get_project_or_raise(session, project_public_id, current_user_public_id)
    if project.id is None:
        raise ProjectNotFoundError("Project not found")

    existing_member = await _get_project_member(session, project.id, user_public_id)
    if existing_member is not None:
        raise ProjectMemberConflictError("Project member already exists")

    member = ProjectMember(
        project_id=project.id,
        user_public_id=user_public_id,
        role=role,
        joined_at=utc_now(),
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    member_read = await _get_project_member_read(session, project.id, user_public_id)
    if member_read is None:
        raise ProjectMemberNotFoundError("Project member not found")
    return member_read


async def invite_project_member(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    role: ProjectMemberRole,
    current_user_public_id: str,
) -> ProjectMemberRead:
    """邀请用户加入项目。"""
    await _get_user_by_public_id_or_raise(session, user_public_id)
    return await add_project_member(
        session,
        project_public_id,
        user_public_id,
        role,
        current_user_public_id,
    )


async def update_project_member_role(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    role: ProjectMemberRole,
    current_user_public_id: str,
) -> ProjectMemberRead:
    """更新项目成员角色。"""
    project = await get_project_or_raise(session, project_public_id, current_user_public_id)
    if project.id is None:
        raise ProjectNotFoundError("Project not found")

    member = await get_project_member_or_raise(
        session,
        project.id,
        user_public_id,
        current_user_public_id,
    )
    member.role = role
    session.add(member)
    await session.commit()
    await session.refresh(member)
    member_read = await _get_project_member_read(session, project.id, user_public_id)
    if member_read is None:
        raise ProjectMemberNotFoundError("Project member not found")
    return member_read


async def remove_project_member(
    session: AsyncSession,
    project_public_id: str,
    user_public_id: str,
    current_user_public_id: str,
) -> None:
    """移除项目成员。"""
    project = await get_project_or_raise(session, project_public_id, current_user_public_id)
    if project.id is None:
        raise ProjectNotFoundError("Project not found")

    member = await get_project_member_or_raise(
        session,
        project.id,
        user_public_id,
        current_user_public_id,
    )
    await session.delete(member)
    await session.commit()


async def _list_project_members_by_project_id(
    session: AsyncSession,
    project_id: int,
) -> list[ProjectMember]:
    """按项目内部主键获取项目成员列表。"""
    statement = (
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.id)
    )
    result = await session.exec(statement)
    return list(result.all())


async def _list_project_member_reads_by_project_id(
    session: AsyncSession,
    project_id: int,
) -> list[ProjectMemberRead]:
    """按项目内部主键获取带用户邮箱的成员响应列表。"""
    statement = (
        select(ProjectMember, User.email)
        .join(User, ProjectMember.user_public_id == User.public_id, isouter=True)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.id)
    )
    result = await session.exec(statement)
    return [
        _build_project_member_read(member, user_email)
        for member, user_email in result.all()
    ]


async def _get_project_member_read(
    session: AsyncSession,
    project_id: int,
    user_public_id: str,
) -> ProjectMemberRead | None:
    """按项目和用户获取带用户邮箱的成员响应。"""
    statement = (
        select(ProjectMember, User.email)
        .join(User, ProjectMember.user_public_id == User.public_id, isouter=True)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_public_id == user_public_id,
        )
    )
    result = await session.exec(statement)
    row = result.first()
    if row is None:
        return None

    member, user_email = row
    return _build_project_member_read(member, user_email)


def _build_project_member_read(member: ProjectMember, user_email: str | None) -> ProjectMemberRead:
    """将成员关系和用户邮箱组装为客户端响应。"""
    if member.id is None:
        raise ProjectServiceError("Project member id was not generated")
    return ProjectMemberRead(
        id=member.id,
        project_id=member.project_id,
        user_public_id=member.user_public_id,
        user_email=user_email,
        role=member.role,
        joined_at=member.joined_at,
    )


async def _get_current_user_or_raise(session: AsyncSession, current_user_public_id: str) -> User:
    """获取当前用户，不存在时按项目访问拒绝处理。"""
    statement = select(User).where(User.public_id == current_user_public_id)
    result = await session.exec(statement)
    user = result.first()
    if user is None:
        raise ProjectAccessDeniedError("Project access denied")
    return user


async def _get_user_by_public_id_or_raise(session: AsyncSession, public_id: str) -> User:
    """获取用户，不存在时按成员不存在处理。"""
    statement = select(User).where(User.public_id == public_id)
    result = await session.exec(statement)
    user = result.first()
    if user is None:
        raise ProjectMemberNotFoundError("User not found")
    return user


async def _ensure_superuser(session: AsyncSession, current_user_public_id: str) -> User:
    """确认当前用户是超级管理员。"""
    current_user = await _get_current_user_or_raise(session, current_user_public_id)
    if not current_user.is_superuser:
        raise ProjectAccessDeniedError("Admin privilege required")
    return current_user


async def _ensure_project_access(
    session: AsyncSession,
    project: Project,
    current_user_public_id: str,
) -> None:
    """确认当前用户是否可访问指定项目。"""
    current_user = await _get_current_user_or_raise(session, current_user_public_id)
    if current_user.is_superuser or project.owner_id == current_user_public_id:
        return
    if project.id is not None and await _get_project_member(session, project.id, current_user_public_id):
        return
    raise ProjectAccessDeniedError("Project access denied")


async def _list_accessible_projects(
    session: AsyncSession,
    current_user_public_id: str,
    statement,
) -> list[Project]:
    """执行项目列表查询，并按当前用户权限收敛结果集。"""
    current_user = await _get_current_user_or_raise(session, current_user_public_id)
    if not current_user.is_superuser:
        statement = statement.where(_project_related_to_user_condition(current_user_public_id))

    statement = statement.distinct().order_by(Project.sort_order, Project.id)
    result = await session.exec(statement)
    return list(result.all())


def _project_related_to_user_condition(user_public_id: str):
    """返回项目与用户相关的 SQL 条件。"""
    return or_(
        Project.owner_id == user_public_id,
        _project_has_member_condition(user_public_id),
    )


def _project_has_member_condition(user_public_id: str):
    """返回项目包含指定成员的 SQL 条件。"""
    return exists().where(
        ProjectMember.project_id == Project.id,
        ProjectMember.user_public_id == user_public_id,
    )


async def list_visual_styles(session: AsyncSession) -> list[VisualStyleRead]:
    """列出配置目录中的全部视觉风格。"""
    root = _visual_style_root()
    print("root", root)
    root.mkdir(parents=True, exist_ok=True)
    styles = []
    for style_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        styles.append(_read_visual_style(style_dir.name))
    return styles


async def list_director_manuals(session: AsyncSession) -> list[DirectorManualRead]:
    """列出配置目录中的全部导演手册。"""
    root = _director_manual_root()
    root.mkdir(parents=True, exist_ok=True)
    manuals = []
    for manual_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        manuals.append(_read_director_manual(manual_dir.name))
    return manuals


async def create_director_manual(
    session: AsyncSession,
    current_user_public_id: str,
    payload: DirectorManualCreate,
) -> DirectorManualRead:
    """创建导演手册目录并写入 Markdown 文件和图片。"""
    await _ensure_superuser(session, current_user_public_id)
    manual_dir = _director_manual_dir(payload.manual_path)
    if manual_dir.exists():
        raise DirectorManualConflictError("Director manual already exists")

    manual_dir.mkdir(parents=True)
    _write_default_director_readme_if_needed(manual_dir, payload.name, payload.files)
    for file_payload in payload.files:
        _write_director_manual_file_unchecked(manual_dir, file_payload)
    for image_payload in payload.images:
        _write_director_manual_image_unchecked(manual_dir, image_payload)
    return _read_director_manual(manual_dir.name)


async def get_director_manual_image_path(
    session: AsyncSession,
    manual_path: str,
    filename: str,
) -> Path:
    """返回导演手册图片的本地路径。"""
    manual_dir = _existing_director_manual_dir(manual_path)
    target = _resolve_director_manual_image_file(manual_dir, filename)
    if not target.exists() or not target.is_file():
        raise DirectorManualNotFoundError("Director manual image not found")
    return target


async def read_director_manual_file(
    session: AsyncSession,
    manual_path: str,
    file_path: str,
) -> DirectorManualFileRead:
    """读取导演手册目录中的单个 Markdown 文件。"""
    manual_dir = _existing_director_manual_dir(manual_path)
    target = _resolve_director_manual_markdown_file(manual_dir, file_path)
    if not target.exists() or not target.is_file():
        raise DirectorManualNotFoundError("Director manual file not found")
    return _read_director_manual_file(manual_dir, target)


async def write_director_manual_file(
    session: AsyncSession,
    manual_path: str,
    payload: DirectorManualFileWrite,
) -> DirectorManualFileRead:
    """新增或覆盖导演手册目录中的单个 Markdown 文件。"""
    manual_dir = _existing_director_manual_dir(manual_path)
    target = _resolve_director_manual_markdown_file(manual_dir, payload.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    return _read_director_manual_file(manual_dir, target)


async def delete_director_manual_file(
    session: AsyncSession,
    current_user_public_id: str,
    manual_path: str,
    file_path: str,
) -> None:
    """删除导演手册目录中的单个 Markdown 文件。"""
    await _ensure_superuser(session, current_user_public_id)
    manual_dir = _existing_director_manual_dir(manual_path)
    target = _resolve_director_manual_markdown_file(manual_dir, file_path)
    if not target.exists() or not target.is_file():
        raise DirectorManualNotFoundError("Director manual file not found")
    target.unlink()


async def write_director_manual_image(
    session: AsyncSession,
    manual_path: str,
    payload: DirectorManualImageWrite,
) -> DirectorManualImageRead:
    """新增或覆盖导演手册目录中的单个图片。"""
    manual_dir = _existing_director_manual_dir(manual_path)
    target = _resolve_director_manual_image_file(manual_dir, payload.filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_decode_director_manual_image_data(payload.data))
    return _read_director_manual_image(manual_dir, target)


async def delete_director_manual_image(
    session: AsyncSession,
    manual_path: str,
    filename: str,
) -> None:
    """删除导演手册目录中的单个图片。"""
    manual_dir = _existing_director_manual_dir(manual_path)
    target = _resolve_director_manual_image_file(manual_dir, filename)
    if not target.exists() or not target.is_file():
        raise DirectorManualNotFoundError("Director manual image not found")
    target.unlink()


async def get_visual_style(
    session: AsyncSession,
    style_path: str,
) -> VisualStyleRead:
    """读取单个视觉风格的 Markdown 文件和图片元数据。"""
    style_dir = _existing_visual_style_dir(style_path)
    return _read_visual_style(style_dir.name)


async def create_visual_style(
    session: AsyncSession,
    current_user_public_id: str,
    payload: VisualStyleCreate,
) -> VisualStyleRead:
    """创建视觉风格目录并写入 Markdown 文件和图片。"""
    await _ensure_superuser(session, current_user_public_id)
    style_dir = _visual_style_dir(payload.style_path)
    if style_dir.exists():
        raise VisualStyleConflictError("Visual style already exists")

    style_dir.mkdir(parents=True)
    _write_default_readme_if_needed(style_dir, payload.name, payload.files)
    for file_payload in payload.files:
        _write_visual_style_file_unchecked(style_dir, file_payload)
    for image_payload in payload.images:
        _write_visual_style_image_unchecked(style_dir, image_payload)
    return _read_visual_style(payload.style_path)


async def update_visual_style(
    session: AsyncSession,
    current_user_public_id: str,
    style_path: str,
    payload: VisualStyleUpdate,
) -> VisualStyleRead:
    """更新视觉风格 Markdown 文件和图片。"""
    await _ensure_superuser(session, current_user_public_id)
    style_dir = _existing_visual_style_dir(style_path)

    if payload.name and not _payload_contains_file(payload.files, "README.md"):
        _write_visual_style_file_unchecked(
            style_dir,
            VisualStyleFileWrite(path="README.md", content=f"# {payload.name}\n"),
        )
    for file_payload in payload.files or []:
        _write_visual_style_file_unchecked(style_dir, file_payload)

    if payload.replace_images:
        images_dir = style_dir / IMAGES_DIR_NAME
        if images_dir.exists():
            for image_path in images_dir.iterdir():
                if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS:
                    image_path.unlink()
    for image_payload in payload.images or []:
        _write_visual_style_image_unchecked(style_dir, image_payload)

    return _read_visual_style(style_dir.name)


async def delete_visual_style(
    session: AsyncSession,
    current_user_public_id: str,
    style_path: str,
) -> None:
    """删除视觉风格目录。"""
    await _ensure_superuser(session, current_user_public_id)
    style_dir = _existing_visual_style_dir(style_path)
    shutil.rmtree(style_dir)


async def read_visual_style_file(
    session: AsyncSession,
    style_path: str,
    file_path: str,
) -> VisualStyleFileRead:
    """读取视觉风格目录中的单个 Markdown 文件。"""
    style_dir = _existing_visual_style_dir(style_path)
    target = _resolve_markdown_file(style_dir, file_path)
    if not target.exists() or not target.is_file():
        raise VisualStyleNotFoundError("Visual style file not found")
    return _read_visual_style_file(style_dir, target)


async def write_visual_style_file(
    session: AsyncSession,
    style_path: str,
    payload: VisualStyleFileWrite,
) -> VisualStyleFileRead:
    """新增或覆盖视觉风格目录中的单个 Markdown 文件。"""
    style_dir = _visual_style_dir(style_path)
    target = _resolve_markdown_file(style_dir, payload.path)
    if not style_dir.exists():
        raise VisualStyleNotFoundError("Visual style not found")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    return _read_visual_style_file(style_dir, target)


async def delete_visual_style_file(
    session: AsyncSession,
    current_user_public_id: str,
    style_path: str,
    file_path: str,
) -> None:
    """删除视觉风格目录中的单个 Markdown 文件。"""
    await _ensure_superuser(session, current_user_public_id)
    style_dir = _existing_visual_style_dir(style_path)
    target = _resolve_markdown_file(style_dir, file_path)
    if not target.exists() or not target.is_file():
        raise VisualStyleNotFoundError("Visual style file not found")
    target.unlink()


async def get_visual_style_image_path(
    session: AsyncSession,
    style_path: str,
    filename: str,
) -> Path:
    """返回视觉风格图片的本地路径。"""
    style_dir = _existing_visual_style_dir(style_path)
    target = _resolve_image_file(style_dir, filename)
    if not target.exists() or not target.is_file():
        raise VisualStyleNotFoundError("Visual style image not found")
    return target


async def write_visual_style_image(
    session: AsyncSession,
    style_path: str,
    payload: VisualStyleImageWrite,
) -> VisualStyleImageRead:
    """新增或覆盖视觉风格目录中的单个图片。"""
    style_dir = _existing_visual_style_dir(style_path)
    return _write_visual_style_image_unchecked(style_dir, payload)


async def delete_visual_style_image(
    session: AsyncSession,
    style_path: str,
    filename: str,
) -> None:
    """删除视觉风格目录中的单个图片。"""
    style_dir = _existing_visual_style_dir(style_path)
    target = _resolve_image_file(style_dir, filename)
    if not target.exists() or not target.is_file():
        raise VisualStyleNotFoundError("Visual style image not found")
    target.unlink()


def _visual_style_root() -> Path:
    """返回配置中的视觉风格根目录。"""
    configured = Path(settings.visual_style_root).expanduser()
    root = configured if configured.is_absolute() else BASE_DIR / configured
    return root.resolve()


def _visual_style_dir(style_path: str) -> Path:
    """解析并校验视觉风格目录路径。"""
    safe_style_path = _validate_style_path(style_path)
    root = _visual_style_root()
    style_dir = (root / safe_style_path).resolve()
    _ensure_path_inside(style_dir, root)
    return style_dir


def _director_manual_root() -> Path:
    """返回配置中的导演手册根目录。"""
    configured = Path(settings.director_manual_root).expanduser()
    root = configured if configured.is_absolute() else BASE_DIR / configured
    return root.resolve()


def _director_manual_dir(manual_path: str) -> Path:
    """解析并校验导演手册目录路径。"""
    safe_manual_path = _validate_director_manual_path(manual_path)
    root = _director_manual_root()
    manual_dir = (root / safe_manual_path).resolve()
    _ensure_director_manual_path_inside(manual_dir, root)
    return manual_dir


def _existing_director_manual_dir(manual_path: str) -> Path:
    """解析已存在的导演手册目录。"""
    manual_dir = _director_manual_dir(manual_path)
    if not manual_dir.exists() or not manual_dir.is_dir():
        raise DirectorManualNotFoundError("Director manual not found")
    return manual_dir


def _validate_director_manual_path(manual_path: str) -> str:
    """校验导演手册目录名，避免路径穿越。"""
    value = manual_path.strip()
    if not STYLE_PATH_PATTERN.fullmatch(value) or value in {".", ".."} or value.isdigit():
        raise DirectorManualValidationError("Invalid director manual path")
    return value


def _resolve_director_manual_image_file(manual_dir: Path, filename: str) -> Path:
    """解析导演手册 images 子目录内的图片路径。"""
    raw = filename.strip()
    path = Path(raw)
    if not raw or path.name != raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise DirectorManualValidationError("Invalid director manual image filename")
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise DirectorManualValidationError("Unsupported director manual image extension")

    images_dir = (manual_dir / IMAGES_DIR_NAME).resolve()
    target = (images_dir / path.name).resolve()
    _ensure_director_manual_path_inside(target, images_dir)
    return target


def _resolve_director_manual_markdown_file(manual_dir: Path, file_path: str) -> Path:
    """解析导演手册目录内的 Markdown 文件路径。"""
    raw = file_path.strip().replace("\\", "/")
    path = Path(raw)
    if not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise DirectorManualValidationError("Invalid director manual file path")
    if path.suffix.lower() != ".md":
        raise DirectorManualValidationError("Director manual file must be a .md file")
    if path.parts[0].lower() == IMAGES_DIR_NAME:
        raise DirectorManualValidationError("Markdown files cannot be written under images")

    target = (manual_dir / path).resolve()
    _ensure_director_manual_path_inside(target, manual_dir)
    return target


def _ensure_director_manual_path_inside(path: Path, root: Path) -> None:
    """确保目标路径没有逃逸出指定根目录。"""
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise DirectorManualValidationError("Path escapes director manual root") from exc


def _existing_visual_style_dir(style_path: str) -> Path:
    """解析已存在的视觉风格目录。"""
    style_dir = _visual_style_dir(style_path)
    if not style_dir.exists() or not style_dir.is_dir():
        raise VisualStyleNotFoundError("Visual style not found")
    return style_dir


def _validate_style_path(style_path: str) -> str:
    """校验风格目录名，避免路径穿越和误删无关目录。"""
    value = style_path.strip()
    if not STYLE_PATH_PATTERN.fullmatch(value) or value in {".", ".."} or value.isdigit():
        raise VisualStyleValidationError("Invalid visual style path")
    return value


def _resolve_markdown_file(style_dir: Path, file_path: str) -> Path:
    """解析风格目录内的 Markdown 文件路径。"""
    raw = file_path.strip().replace("\\", "/")
    path = Path(raw)
    if not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise VisualStyleValidationError("Invalid visual style file path")
    if path.suffix.lower() != ".md":
        raise VisualStyleValidationError("Visual style file must be a .md file")
    if path.parts[0].lower() == IMAGES_DIR_NAME:
        raise VisualStyleValidationError("Markdown files cannot be written under images")

    target = (style_dir / path).resolve()
    _ensure_path_inside(target, style_dir)
    return target


def _resolve_image_file(style_dir: Path, filename: str) -> Path:
    """解析风格目录 images 子目录内的图片路径。"""
    raw = filename.strip()
    path = Path(raw)
    if not raw or path.name != raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise VisualStyleValidationError("Invalid visual style image filename")
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise VisualStyleValidationError("Unsupported visual style image extension")

    images_dir = (style_dir / IMAGES_DIR_NAME).resolve()
    target = (images_dir / path.name).resolve()
    _ensure_path_inside(target, images_dir)
    return target


def _ensure_path_inside(path: Path, root: Path) -> None:
    """确保目标路径没有逃逸出指定根目录。"""
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise VisualStyleValidationError("Path escapes visual style root") from exc


def _read_visual_style(style_path: str) -> VisualStyleRead:
    """从文件系统读取视觉风格完整数据。"""
    style_dir = _existing_visual_style_dir(style_path)
    files = [
        _read_visual_style_file(style_dir, file_path)
        for file_path in sorted(style_dir.rglob("*.md"))
        if file_path.is_file()
    ]
    images_dir = style_dir / IMAGES_DIR_NAME
    images = []
    if images_dir.exists() and images_dir.is_dir():
        images = [
            _read_visual_style_image(style_dir, image_path)
            for image_path in sorted(images_dir.iterdir())
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS
        ]
    return VisualStyleRead(
        style_path=style_dir.name,
        name=_read_visual_style_name(style_dir),
        files=files,
        images=images,
    )


def _read_director_manual(manual_path: str) -> DirectorManualRead:
    """从文件系统读取导演手册完整数据。"""
    manual_dir = _existing_director_manual_dir(manual_path)
    files = [
        _read_director_manual_file(manual_dir, file_path)
        for file_path in sorted(manual_dir.rglob("*.md"))
        if file_path.is_file()
    ]
    images_dir = manual_dir / IMAGES_DIR_NAME
    images = []
    if images_dir.exists() and images_dir.is_dir():
        images = [
            _read_director_manual_image(manual_dir, image_path)
            for image_path in sorted(images_dir.iterdir())
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS
        ]
    return DirectorManualRead(
        manual_path=manual_dir.name,
        name=_read_director_manual_name(manual_dir),
        files=files,
        images=images,
    )


def _read_visual_style_file(style_dir: Path, file_path: Path) -> VisualStyleFileRead:
    """读取单个 Markdown 文件。"""
    return VisualStyleFileRead(
        path=file_path.relative_to(style_dir).as_posix(),
        content=file_path.read_text(encoding="utf-8"),
        size_bytes=file_path.stat().st_size,
    )


def _read_director_manual_file(manual_dir: Path, file_path: Path) -> DirectorManualFileRead:
    """读取单个导演手册 Markdown 文件。"""
    return DirectorManualFileRead(
        path=file_path.relative_to(manual_dir).as_posix(),
        content=file_path.read_text(encoding="utf-8"),
        size_bytes=file_path.stat().st_size,
    )


def _read_visual_style_image(style_dir: Path, image_path: Path) -> VisualStyleImageRead:
    """读取单个图片元数据。"""
    filename = image_path.name
    return VisualStyleImageRead(
        filename=filename,
        path=image_path.relative_to(style_dir).as_posix(),
        url=_visual_style_image_url(style_dir.name, filename),
        size_bytes=image_path.stat().st_size,
    )


def _read_director_manual_image(manual_dir: Path, image_path: Path) -> DirectorManualImageRead:
    """读取单个导演手册图片元数据。"""
    filename = image_path.name
    return DirectorManualImageRead(
        filename=filename,
        path=image_path.relative_to(manual_dir).as_posix(),
        url=_director_manual_image_url(manual_dir.name, filename),
        size_bytes=image_path.stat().st_size,
    )


def _visual_style_image_url(style_path: str, filename: str) -> str:
    """构建可直接给浏览器访问的视觉风格图片 URL。"""
    api_prefix = settings.api_prefix.strip()
    if api_prefix and not api_prefix.startswith("/"):
        api_prefix = f"/{api_prefix}"
    api_prefix = api_prefix.rstrip("/")
    return (
        f"{api_prefix}/projects/visual-styles/"
        f"{quote(style_path, safe='')}/images/{quote(filename, safe='')}"
    )


def _director_manual_image_url(manual_path: str, filename: str) -> str:
    """构建可直接给浏览器访问的导演手册图片 URL。"""
    api_prefix = settings.api_prefix.strip()
    if api_prefix and not api_prefix.startswith("/"):
        api_prefix = f"/{api_prefix}"
    api_prefix = api_prefix.rstrip("/")
    return (
        f"{api_prefix}/projects/director-manuals/"
        f"{quote(manual_path, safe='')}/images/{quote(filename, safe='')}"
    )


def _write_visual_style_file_unchecked(style_dir: Path, payload: VisualStyleFileWrite) -> VisualStyleFileRead:
    """写入 Markdown 文件；调用方负责权限和风格目录存在性。"""
    target = _resolve_markdown_file(style_dir, payload.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    return _read_visual_style_file(style_dir, target)


def _write_visual_style_image_unchecked(style_dir: Path, payload: VisualStyleImageWrite) -> VisualStyleImageRead:
    """写入图片；调用方负责权限和风格目录存在性。"""
    target = _resolve_image_file(style_dir, payload.filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_decode_image_data(payload.data))
    return _read_visual_style_image(style_dir, target)


def _write_director_manual_file_unchecked(manual_dir: Path, payload: DirectorManualFileWrite) -> DirectorManualFileRead:
    """写入导演手册 Markdown 文件；调用方负责权限和目录存在性。"""
    target = _resolve_director_manual_markdown_file(manual_dir, payload.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    return _read_director_manual_file(manual_dir, target)


def _write_director_manual_image_unchecked(manual_dir: Path, payload: DirectorManualImageWrite) -> DirectorManualImageRead:
    """写入导演手册图片；调用方负责权限和目录存在性。"""
    target = _resolve_director_manual_image_file(manual_dir, payload.filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_decode_director_manual_image_data(payload.data))
    return _read_director_manual_image(manual_dir, target)


def _decode_image_data(data: str) -> bytes:
    """解码 base64 图片内容。"""
    raw = data.split(",", 1)[1] if data.startswith("data:") and "," in data else data
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise VisualStyleValidationError("Invalid image base64 data") from exc


def _decode_director_manual_image_data(data: str) -> bytes:
    """解码导演手册 base64 图片内容。"""
    raw = data.split(",", 1)[1] if data.startswith("data:") and "," in data else data
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DirectorManualValidationError("Invalid image base64 data") from exc


def _read_visual_style_name(style_dir: Path) -> str:
    """从 README 第一行提取风格展示名称。"""
    readme = style_dir / "README.md"
    if not readme.exists():
        return style_dir.name
    for line in readme.read_text(encoding="utf-8").splitlines():
        value = line.strip().lstrip("#").strip()
        if value:
            return value
    return style_dir.name


def _read_director_manual_name(manual_dir: Path) -> str:
    """从 README 第一行提取导演手册展示名称。"""
    readme = manual_dir / "README.md"
    if not readme.exists():
        return manual_dir.name
    for line in readme.read_text(encoding="utf-8").splitlines():
        value = line.strip().lstrip("#").strip()
        if value:
            return value
    return manual_dir.name


def _write_default_readme_if_needed(
    style_dir: Path,
    name: str,
    files: list[VisualStyleFileWrite],
) -> None:
    """创建风格时如果只给了名称，则补一个 README。"""
    if not name or _payload_contains_file(files, "README.md"):
        return
    _write_visual_style_file_unchecked(style_dir, VisualStyleFileWrite(path="README.md", content=f"# {name}\n"))


def _write_default_director_readme_if_needed(
    manual_dir: Path,
    name: str,
    files: list[DirectorManualFileWrite],
) -> None:
    """创建导演手册时如果只给了名称，则补一个 README。"""
    if not name or _director_payload_contains_file(files, "README.md"):
        return
    _write_director_manual_file_unchecked(
        manual_dir,
        DirectorManualFileWrite(path="README.md", content=f"# {name}\n"),
    )


def _payload_contains_file(files: list[VisualStyleFileWrite] | None, file_path: str) -> bool:
    """判断文件写入列表中是否包含指定相对路径。"""
    expected = file_path.replace("\\", "/").lower()
    return any(item.path.replace("\\", "/").lower() == expected for item in files or [])


def _director_payload_contains_file(files: list[DirectorManualFileWrite] | None, file_path: str) -> bool:
    """判断导演手册写入列表中是否包含指定相对路径。"""
    expected = file_path.replace("\\", "/").lower()
    return any(item.path.replace("\\", "/").lower() == expected for item in files or [])