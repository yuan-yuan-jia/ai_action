# AI 知识库 编码规范 V0.1

## 要做什么
- Python 用 black 格式化（默认 88 字符），配置写入 pyproject.toml
- 用 ruff 做 import 排序 + lint，配置写入 pyproject.toml
- 所有公开函数必须有 Google 风格 docstring（含 Args / Returns / Raises）
- 统一使用 `logging` 模块，禁止裸 `print()`
- 文件/目录命名使用 `snake_case`
- import 使用绝对路径（如 `from ai_project.module import foo`）

- 所有函数（含私有）必须标注类型 hint
- 自定义异常继承 `AppError`（项目级基类）

## 不做什么
- 禁止业务逻辑中的裸字符串/数字字面量；应定义为模块级命名常量（如 `MAX_RETRIES = 3`）
  - 异常消息、日志模板、ENV key 名不在此限
- 不允许 TODO 提交到 main

## 边界和验收
- 使用 pytest + pytest-cov（配置在 pyproject.toml）
- line coverage >= 80%，CI 不达标则失败

## 怎么验证
- 本地：pre-commit hook（black + ruff + TODO 拦截）
- CI：GitHub Actions（`.github/workflows/ci.yml`），运行 ruff check . && pytest --cov
