# PhD 申请协作平台

用于导师筛选、套磁跟踪、申请跟踪、文书版本和可选 AI 辅助的轻量 Web 应用。

本仓库是旧版平台的独立脱敏快照，不包含后续功能更新，也不连接维护者的运行环境。示例导师、学校和链接均为虚构；没有真实申请材料、套磁信、备注、数据库、上传文件或服务凭据。

## 环境要求

- Python 3.10 或更高版本。
- SQLite 使用 Python 标准库；MySQL 模式另需 MySQL 和 `PyMySQL`。
- 浏览器无需安装前端依赖。

## 本地运行

在本仓库根目录执行：

```bash
cp .env.example .env
```

编辑未纳入 Git 的 `.env`，将 `PHD_PLATFORM_ACCOUNTS` 中的占位密码替换为自己设置的密码。所有环境都必须显式配置账号，仓库没有可用的默认密码。

```bash
python3 server.py --host 127.0.0.1 --port 8765
```

打开 <http://127.0.0.1:8765>，使用自己配置的账号登录。首次运行会在 `data/` 创建独立 SQLite 数据库，导入三条虚构导师示例和三个空文书台账条目；台账条目不是申请材料正文。

## MySQL 模式

在自己的 MySQL 实例创建专用数据库和低权限应用账号，在 `.env` 中配置：

```text
PHD_PLATFORM_DB_BACKEND=mysql
PHD_PLATFORM_MYSQL_HOST=127.0.0.1
PHD_PLATFORM_MYSQL_PORT=3306
PHD_PLATFORM_MYSQL_DATABASE=phd_workspace
PHD_PLATFORM_MYSQL_USER=phd_app
PHD_PLATFORM_MYSQL_PASSWORD=替换为自己的数据库密码
```

```bash
python3 -m pip install PyMySQL
bash scripts/run_local_mysql.sh
```

`scripts/migrate_sqlite_to_mysql.py` 可用于迁移自己的数据。先阅读脚本参数并做备份；不要对他人的数据库执行导入或清理脚本。

## 数据和材料

- `seed/demo_advisors.html` 只包含三条虚构示例。自行准备的数据可通过 `PHD_PLATFORM_SEED_HTML` 指向相同 `candidate-data` JSON 格式的 HTML 文件。
- 运行数据、备注、账号配置、材料上传和备份均不应提交到 Git。
- `data/document_uploads/` 是用户上传副本；仓库不包含这些文件。
- AI 功能默认关闭。使用时自行配置服务，提交的上下文可能包含导师信息和自己上传的 CV 摘要，应先确认数据适合发送给所选服务。
- 旧版辅助脚本含数据导入、删除和清理能力，只应在自己授权管理的环境中使用。

## 公网部署

1. 应用仅监听回环地址，由反向代理提供 HTTPS。
2. 在私有环境变量中配置自己设置的强密码；不要使用模板占位值。
3. 设置 `PHD_PLATFORM_ENV=production`、`PHD_PLATFORM_COOKIE_SECURE=1`。
4. AI Key 仅通过 `PHD_PLATFORM_AI_API_KEY` 提供，不提交到 Git，也不写入公开配置。
5. 不公开数据库端口、整个项目目录、上传材料、日志或备份；定期备份自己的数据。

这是独立运行的源码快照，不附带托管服务、生产数据或任何现有网站的访问权限。
