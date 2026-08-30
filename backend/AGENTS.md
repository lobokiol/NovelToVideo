# Repository Guidelines

## 项目结构与模块组织

本仓库以后端应用和配套运行服务为核心。后端源码应放在 `backend/app` 下，并按职责拆分为路由、服务、模型、数据结构、后台任务和配置等模块。测试应放在 `tests/`，或放在与源码结构对应的既有测试目录中。需求、开发记录和运行说明优先放在 `docs/` 或仓库已有文档位置。

除非任务明确要求，不要新增无关顶层目录、搬迁文件或重构目录结构。优先复用已有模块、工具函数和配置。

## 构建、测试与本地开发命令

本地服务优先使用项目现有 Docker Compose 工作流：

```powershell
docker compose up -d --build backend worker
docker compose ps
docker logs --tail 120 ai-novel-backend
docker logs --tail 120 ai-novel-worker
```

后端轻量级语法与导入检查可使用：

```powershell
python -m compileall backend/app
```

如仓库存在测试配置，优先使用项目定义的入口，例如 `pytest`、`python -m pytest` 或 `uv run pytest`。在确认配置前，不要擅自引入新的包管理器、测试框架或运行命令。

## 代码风格与命名约定

Python 代码遵循仓库既有风格；若无更具体约定，按 PEP 8 和 PEP 484 编写。函数和变量使用 `snake_case`，类名使用 `PascalCase`，常量使用 `UPPER_SNAKE_CASE`。保持函数短小、职责单一，副作用集中在明确边界内。

新增代码应优先使用明确类型标注。异常处理要具体、可诊断，避免裸 `except`。配置必须来自既有配置系统或环境变量，不要硬编码密钥、端口、服务地址或生产凭据。

## 测试规范

涉及行为变化时，应新增或更新测试。测试文件应尽量镜像源码结构，例如 `tests/test_auth.py` 或 `tests/services/test_novel_service.py`。测试函数名应描述被验证行为，例如 `test_login_rejects_invalid_password`。

修复缺陷时，优先补充回归测试。若自动化测试暂不可用，必须记录清晰的手工验证步骤、执行命令和实际结果。

## 提交与 Pull Request 规范

提交信息使用简洁的 Conventional Commits 风格，例如：

```text
feat(sprint1): bootstrap project scaffold
docs(clerk): record sprint kickoff
```

PR 应说明问题背景、改动内容、验证命令与结果，以及是否存在配置、迁移或兼容性影响。关联相关 issue、需求文档或开发记录。仅在涉及界面变化时附截图。

## Agent 执行规范

修改前先阅读相关代码、配置、测试和相似实现。默认采用最小必要改动，不顺手重构无关代码，不扩大任务范围。完成后运行与改动直接相关的验证，并如实报告通过、失败或无法执行的原因。

不得伪造测试结果，不得提交密钥、令牌、证书或真实个人数据。任何可能影响数据、权限、认证或生产配置的改动，都必须明确说明影响范围和回滚方式。
