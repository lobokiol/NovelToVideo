from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.project import ProjectMemberRole, ProjectVideoMode


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="项目名称")
    intro: str = Field(default="", max_length=2000, description="项目简介")
    project_type: str = Field(default="novel_to_video", description="项目类型")
    content_type: str = Field(default="novel", description="内容来源类型")
    art_style: str = Field(default="3D_chinese_traditional", description="艺术风格")
    director_manual: str = Field(default="", description="导演风格")
    video_ratio: str = Field(default="9:16", description="视频比例")
    text_model: str = Field(default="", description="文本模型")
    image_model: str = Field(default="", description="生图模型")
    video_model: str = Field(default="", description="视频模型")
    tts_model: str = Field(default="", description="语音模型")
    image_quality: str = Field(default="standard", description="图片质量")
    mode: ProjectVideoMode = Field(default=ProjectVideoMode.TEXT, description="视频生成模式")


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    intro: str | None = None
    project_type: str | None = None
    content_type: str | None = None
    art_style: str | None = None
    director_manual: str | None = None
    video_ratio: str | None = None
    text_model: str | None = None
    image_model: str | None = None
    video_model: str | None = None
    tts_model: str | None = None
    image_quality: str | None = None
    mode: ProjectVideoMode | None = None


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: str
    owner_id: str
    my_role: ProjectMemberRole | None = None
    sort_order: int
    created_at: datetime
    updated_at: datetime
    disabled_at: datetime | None


class ProjectMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    user_public_id: str
    user_email: str | None
    role: ProjectMemberRole
    joined_at: datetime


class ProjectMemberInvite(BaseModel):
    user_public_id: str = Field(min_length=1, max_length=36, description="被邀请用户的公开标识")
    role: ProjectMemberRole = Field(default=ProjectMemberRole.VIEWER, description="邀请加入后的项目角色")


class VisualStyleFileRead(BaseModel):
    """视觉风格 Markdown 文件读取结果。"""

    path: str = Field(description="相对于风格目录的 Markdown 文件路径。")
    content: str = Field(description="Markdown 文件内容。")
    size_bytes: int = Field(ge=0, description="文件大小，单位字节。")


class VisualStyleFileWrite(BaseModel):
    """视觉风格 Markdown 文件写入请求。"""

    path: str = Field(default="", max_length=255, description="相对于风格目录的 Markdown 文件路径。")
    content: str = Field(default="", description="Markdown 文件内容。")

    @field_validator("path")
    @classmethod
    def validate_markdown_path(cls, value: str) -> str:
        if value and not value.lower().endswith(".md"):
            raise ValueError("视觉风格文件必须是 .md 文件")
        return value


class VisualStyleImageRead(BaseModel):
    """视觉风格图片读取结果。"""

    filename: str = Field(description="图片文件名。")
    path: str = Field(description="相对于风格目录的图片路径。")
    url: str = Field(description="可直接用于 CSS url() 或 HTML src 的图片访问 URL。")
    size_bytes: int = Field(ge=0, description="文件大小，单位字节。")


class VisualStyleImageWrite(BaseModel):
    """视觉风格图片写入请求。"""

    filename: str = Field(default="", max_length=120, description="图片文件名。")
    data: str = Field(description="图片 base64 内容，可包含 data URI 前缀。")


class VisualStyleRead(BaseModel):
    """视觉风格完整读取结果。"""

    style_path: str = Field(description="视觉风格目录名。")
    name: str = Field(default="", description="视觉风格展示名称。")
    files: list[VisualStyleFileRead] = Field(default_factory=list, description="Markdown 文件列表。")
    images: list[VisualStyleImageRead] = Field(default_factory=list, description="图片文件列表。")


class VisualStyleCreate(BaseModel):
    """创建视觉风格请求。"""

    style_path: str = Field(min_length=1, max_length=120, description="视觉风格目录名。")
    name: str = Field(default="", max_length=120, description="视觉风格展示名称。")
    files: list[VisualStyleFileWrite] = Field(default_factory=list, description="需要写入的 Markdown 文件。")
    images: list[VisualStyleImageWrite] = Field(default_factory=list, description="需要写入的图片。")


class VisualStyleUpdate(BaseModel):
    """更新视觉风格请求。"""

    name: str | None = Field(default=None, max_length=120, description="视觉风格展示名称。")
    files: list[VisualStyleFileWrite] | None = Field(default=None, description="需要新增或覆盖的 Markdown 文件。")
    images: list[VisualStyleImageWrite] | None = Field(default=None, description="需要新增或覆盖的图片。")
    replace_images: bool = Field(default=False, description="是否先清空 images 目录下已有图片。")


class DirectorManualFileRead(BaseModel):
    """导演手册 Markdown 文件读取结果。"""

    path: str = Field(description="相对于导演手册目录的 Markdown 文件路径。")
    content: str = Field(description="Markdown 文件内容。")
    size_bytes: int = Field(ge=0, description="文件大小，单位字节。")


class DirectorManualFileWrite(BaseModel):
    """导演手册 Markdown 文件写入请求。"""

    path: str = Field(default="", max_length=255, description="相对于导演手册目录的 Markdown 文件路径。")
    content: str = Field(default="", description="Markdown 文件内容。")

    @field_validator("path")
    @classmethod
    def validate_markdown_path(cls, value: str) -> str:
        if value and not value.lower().endswith(".md"):
            raise ValueError("导演手册文件必须是 .md 文件")
        return value


class DirectorManualImageRead(BaseModel):
    """导演手册图片读取结果。"""

    filename: str = Field(description="图片文件名。")
    path: str = Field(description="相对于导演手册目录的图片路径。")
    url: str = Field(description="可直接用于 CSS url() 或 HTML src 的图片访问 URL。")
    size_bytes: int = Field(ge=0, description="文件大小，单位字节。")


class DirectorManualImageWrite(BaseModel):
    """导演手册图片写入请求。"""

    filename: str = Field(default="", max_length=120, description="图片文件名。")
    data: str = Field(description="图片 base64 内容，可包含 data URI 前缀。")


class DirectorManualRead(BaseModel):
    """导演手册完整读取结果。"""

    manual_path: str = Field(description="导演手册目录名。")
    name: str = Field(default="", description="导演手册展示名称。")
    files: list[DirectorManualFileRead] = Field(default_factory=list, description="Markdown 文件列表。")
    images: list[DirectorManualImageRead] = Field(default_factory=list, description="图片文件列表。")


class DirectorManualCreate(BaseModel):
    """创建导演手册请求。"""

    manual_path: str = Field(min_length=1, max_length=120, description="导演手册目录名。")
    name: str = Field(default="", max_length=120, description="导演手册展示名称。")
    files: list[DirectorManualFileWrite] = Field(default_factory=list, description="需要写入的 Markdown 文件。")
    images: list[DirectorManualImageWrite] = Field(default_factory=list, description="需要写入的图片。")
