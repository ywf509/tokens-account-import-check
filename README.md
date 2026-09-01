# 邮箱账号检查网页

## 启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DB_HOST=127.0.0.1
export DB_PORT=3306
export DB_USER=root
export DB_PASSWORD='你的密码'
export DB_NAME='你的数据库名'
python app.py
```

浏览器打开 <http://127.0.0.1:5000>。

程序查询 `foai_tokens` 表中指定 `platform` 和时间范围内的 `additional` JSON 的 `email` 字段，并忽略 `deleted_at = b'1'` 的记录。页面上的 `platform` 默认值为 `codex`；开始日期默认是 7 天前，结束日期留空表示不限制结束时间。日期筛选使用 `created_at` 字段，适合已导入帐号过期后重新导入的场景。检查结果会显示总数、已存在数和不存在数；存在缺失邮箱时可下载 `missing-emails.txt`。

## Docker Compose 一键部署

服务器安装 Docker 与 Compose 插件后，在本目录执行：

```bash
cp .env.example .env
vim .env  # 填写真实的 MySQL 连接信息
docker compose up -d --build
```

访问 `http://服务器IP:21018`。容器会加入已存在的 Docker 网络 `tokens_default`，并将宿主机 `21018` 端口映射到容器 `5000` 端口。查看日志：

```bash
docker compose logs -f email-checker
```

停止服务：

```bash
docker compose down
```

`.env` 示例：

```dotenv
DB_HOST=你的MySQL主机
DB_PORT=3306
DB_USER=数据库用户
DB_PASSWORD=数据库密码
DB_NAME=数据库名
```

如果 MySQL 也运行在 `tokens_default` 网络中，将 `DB_HOST` 设置为 MySQL 服务名；如果 MySQL 在宿主机上，Linux 环境通常需要将 `DB_HOST` 设置为宿主机可达地址，而不是容器内的 `127.0.0.1`。

首次部署前确认外部网络已经存在：

```bash
docker network inspect tokens_default >/dev/null || docker network create tokens_default
```
