import json
import os
import re
from datetime import date, datetime, timedelta
from io import BytesIO

from flask import Flask, jsonify, render_template, request, send_file

try:
    import pymysql
except ImportError:  # pragma: no cover - shown as a helpful runtime error
    pymysql = None


app = Flask(__name__)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def get_db_connection():
    """Create a short-lived MySQL connection from environment variables."""
    if pymysql is None:
        raise RuntimeError("未安装 pymysql，请先执行 pip install -r requirements.txt")
    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", ""),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=8,
        read_timeout=20,
        write_timeout=20,
    )


def normalize_emails(raw):
    """Parse one email per line (also accepts commas/semicolons), de-duplicated."""
    candidates = re.split(r"[\s,;]+", raw or "")
    seen, valid, invalid = set(), [], []
    for value in candidates:
        email = value.strip().lower()
        if not email:
            continue
        if not EMAIL_RE.match(email):
            invalid.append(email)
        elif email not in seen:
            seen.add(email)
            valid.append(email)
    return valid, invalid


def parse_date(value, field_name):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是 YYYY-MM-DD 格式") from exc


def check_emails(emails, platform="codex", start_date=None, end_date=None):
    """Look up emails stored in additional JSON in foai_tokens."""
    if not emails:
        return set()
    placeholders = ",".join(["%s"] * len(emails))
    conditions = [
        "deleted_at = b'0'",
        "platform = %s",
        "additional IS NOT NULL",
        "JSON_VALID(additional)",
        f"LOWER(JSON_UNQUOTE(JSON_EXTRACT(additional, '$.email'))) IN ({placeholders})",
    ]
    # SQL 条件中的参数顺序是：platform、邮箱列表、开始日期、结束日期。
    params = [platform, *emails]
    if start_date:
        conditions.append("created_at >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("created_at < %s")
        params.append(end_date + timedelta(days=1))
    sql = f"""
        SELECT DISTINCT LOWER(JSON_UNQUOTE(JSON_EXTRACT(additional, '$.email'))) AS email
        FROM foai_tokens
        WHERE {' AND '.join(conditions)}
    """
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return {row["email"] for row in cursor.fetchall() if row.get("email")}
    finally:
        connection.close()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.post("/api/check")
def api_check():
    payload = request.get_json(silent=True) or {}
    platform = str(payload.get("platform") or "codex").strip().lower()
    if not platform:
        platform = "codex"
    if len(platform) > 256:
        return jsonify({"error": "platform 长度不能超过 256 个字符"}), 400
    try:
        start_date = parse_date(payload.get("start_date"), "开始日期")
        end_date = parse_date(payload.get("end_date"), "结束日期")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if start_date and end_date and start_date > end_date:
        return jsonify({"error": "开始日期不能晚于结束日期"}), 400
    emails, invalid = normalize_emails(payload.get("emails", ""))
    if not emails and invalid:
        return jsonify({"error": "没有检测到有效邮箱", "invalid": invalid}), 400
    try:
        existing = check_emails(emails, platform, start_date, end_date)
    except Exception as exc:
        app.logger.exception("Database check failed")
        return jsonify({"error": f"数据库连接或查询失败：{exc}"}), 500

    missing = [email for email in emails if email not in existing]
    return jsonify(
        {
            "total": len(emails),
            "found_count": len(existing),
            "missing_count": len(missing),
            "missing": missing,
            "invalid": invalid,
            "platform": platform,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        }
    )


@app.post("/api/export")
def api_export():
    payload = request.get_json(silent=True) or {}
    missing = payload.get("missing", [])
    if not isinstance(missing, list):
        return jsonify({"error": "导出数据格式错误"}), 400
    content = "\n".join(str(item).strip() for item in missing if str(item).strip())
    return send_file(
        BytesIO((content + ("\n" if content else "")).encode("utf-8")),
        mimetype="text/plain; charset=utf-8",
        as_attachment=True,
        download_name="missing-emails.txt",
    )


if __name__ == "__main__":
    app.run(host=os.getenv("APP_HOST", "127.0.0.1"), port=int(os.getenv("APP_PORT", "5000")), debug=True)
