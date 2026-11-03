#!/usr/bin/env python3
"""赛题合规自检（对照 dify.md 的硬性要求）。

检查项：
  C1  DSL 文件存在且可被 Dify 重新导入（§4.1）
  C2  seekdb 真实承载数据：表/行数/向量索引/全文索引存在（§2.2）
  C3  seekdb 检索真实生效：混合检索能返回命中（§2.2 "实际发挥作用"）
  C4  Dify 应用可运行：workflow 能跑完并产出非空回答（§3.1-1）
  C5  运行说明覆盖 §4.2 六项
  C6  验证样例存在且含必需小节（§4.3）
  C7  交付物不含真实凭证（§4.2 红线）
  C8  证据索引存在且指向的文件都在（§4.3）

用法：
  python3 tools/compliance_check.py            # 只输出报告
  python3 tools/compliance_check.py --log      # 追加写入 docs/progress-log.md
退出码：0 全通过；1 有失败项。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # dify/
API = os.getenv("INN_API", "http://127.0.0.1:8010")
DIFY = os.getenv("DIFY_BASE", "http://127.0.0.1:5001")
COOKIE = os.getenv("DIFY_COOKIE", "/home/ice/dify/run/cookies.txt")
def _local_env() -> dict[str, str]:
    f = Path(__file__).resolve().parent / ".local.env"
    out: dict[str, str] = {}
    if f.is_file():
        for line in f.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


APP_ID = os.getenv("INN_APP_ID") or _local_env().get("INN_APP_ID", "")
DSL = ROOT / "dsl" / "01_inn_chatflow.yml"

results: list[tuple[str, bool, str]] = []


def check(cid: str, name: str, fn):
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"异常：{exc}"
    results.append((f"{cid} {name}", ok, detail))


def http_json(url: str, data: dict | None = None, headers: dict | None = None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers or {})
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode() or "{}")


def cookie_header() -> str:
    try:
        lines = Path(COOKIE).read_text().splitlines()
    except OSError:
        return ""
    parts = []
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("#") and not line.startswith("#HttpOnly_"):
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        f = line.split("\t")
        if len(f) >= 7:
            parts.append(f"{f[5]}={f[6]}")
    return "; ".join(parts)


def csrf_token() -> str:
    try:
        for line in Path(COOKIE).read_text().splitlines():
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_"):]
            f = line.split("\t")
            if len(f) >= 7 and f[5] == "csrf_token":
                return f[6]
    except OSError:
        pass
    return ""


# ------------------------------------------------------------------ C1


def c1_dsl_importable():
    if not DSL.exists():
        return False, "dsl/01_inn_chatflow.yml 不存在"
    yaml_text = DSL.read_text()
    st, d = http_json(
        f"{DIFY}/console/api/apps/imports",
        {"mode": "yaml-content", "yaml_content": yaml_text},
        {"Cookie": cookie_header(), "X-CSRF-Token": csrf_token()},
    )
    if st == 200 and d.get("status", "").startswith("completed"):
        # 导入成功即删除，避免污染工作区
        app_id = d.get("app_id")
        try:
            req = urllib.request.Request(
                f"{DIFY}/console/api/apps/{app_id}",
                method="DELETE",
                headers={"Cookie": cookie_header(), "X-CSRF-Token": csrf_token()},
            )
            urllib.request.urlopen(req, timeout=20).read()
        except Exception:  # noqa: BLE001
            pass
        return True, f"重导入成功（{d.get('status')}，dsl {d.get('imported_dsl_version')}）"
    return False, f"导入失败：{d}"


# ------------------------------------------------------------------ C2/C3


def mysql(sql: str) -> str:
    cmd = [
        "mysql", "-h", os.getenv("SEEKDB_HOST", "127.0.0.1"),
        "-P", os.getenv("SEEKDB_PORT", "2891"),
        "-u", os.getenv("SEEKDB_USER", "root"),
        "-N", "-B", "-e", sql, os.getenv("SEEKDB_DATABASE", "inn"),
    ]
    if os.getenv("SEEKDB_PASSWORD"):
        cmd.insert(6, f"-p{os.environ['SEEKDB_PASSWORD']}")
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:200])
    return out.stdout.strip()


def c2_seekdb_data():
    tables = mysql("SHOW TABLES").split("\n")
    need = {"inn_player", "inn_ledger", "inn_rumor", "inn_line"}
    missing = need - set(tables)
    if missing:
        return False, f"缺表：{missing}"
    vidx = mysql(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema=DATABASE() AND index_name LIKE 'vidx%'"
    )
    ft = mysql(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema=DATABASE() AND index_type='FULLTEXT'"
    )
    lines = mysql("SELECT COUNT(*) FROM inn_line")
    ledger = mysql("SELECT COUNT(*) FROM inn_ledger")
    if vidx == "0" or ft == "0":
        return False, f"缺索引：vector={vidx} fulltext={ft}"
    if int(lines) < 20:
        return False, f"台词库过少：{lines}"
    return True, f"表齐；向量索引 {vidx} 组、全文索引 {ft} 个；台词 {lines} 条、事件 {ledger} 条"


def c3_hybrid_retrieval():
    payload = {
        "player_id": "p_demo01",
        "conversation_id": "chk_hybrid",
        "action_text": "往酒坛里兑水",
        "action_type": "drink",
        "severity": 1,
    }
    st, d = http_json(f"{API}/inn/ledger", payload)
    if st != 200 or not d.get("similar"):
        return False, f"混合检索无命中：{str(d)[:200]}"
    top = d["similar"][0]
    if not top.get("fulltext_hit") and not top.get("vsim"):
        return False, "命中项既无全文也无向量分数"
    return True, (
        f"命中 {len(d['similar'])} 条，Top1={top['text']}"
        f"(vsim={top['vsim']}, ft={top['fulltext_hit']}, score={top['score']})"
    )


# ------------------------------------------------------------------ C4


def c4_app_runs():
    if not APP_ID:
        return False, "未设置 INN_APP_ID，跳过运行检查"
    payload = {"inputs": {"player_id": "p_demo01"}, "files": [], "query": "往酒坛里兑半坛水"}
    req = urllib.request.Request(
        f"{DIFY}/console/api/apps/{APP_ID}/advanced-chat/workflows/draft/run",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie_header(),
            "X-CSRF-Token": csrf_token(),
        },
    )
    answer = []
    status = None
    final_answer = ""
    with urllib.request.urlopen(req, timeout=180) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except Exception:  # noqa: BLE001
                continue
            if ev.get("event") == "text_chunk":
                answer.append(ev.get("data", {}).get("text", ""))
            if ev.get("event") == "workflow_finished":
                d = ev.get("data", {}) or {}
                status = d.get("status")
                final_answer = str((d.get("outputs") or {}).get("answer") or "")
            if ev.get("event") == "message":
                answer.append(ev.get("answer") or "")
    text = (final_answer or "".join(answer)).strip()
    if status != "succeeded":
        return False, f"workflow 状态 {status}"
    if len(text) < 20:
        return False, f"回答过短：{text[:80]!r}"
    return True, f"workflow succeeded，回答 {len(text)} 字"


# ------------------------------------------------------------------ C9（可选层）


def c9_powercontext():
    st, d = http_json(f"{API}/healthz")
    if not d.get("powercontext"):
        return True, "未启用 PowerContext（赛题只需 seekdb，允许）"
    try:
        urllib.request.urlopen(f"{os.getenv('PC_BASE_URL', 'http://127.0.0.1:8090')}/health/ready", timeout=5)
    except Exception as exc:  # noqa: BLE001
        return False, f"PC 未就绪：{exc}"
    payload = {"player_id": "p_demo01", "action_text": "在醋坛子里洗手", "action_type": "hygiene",
               "severity": 1, "scene": "后厨"}
    http_json(f"{API}/inn/ledger", payload)
    with urllib.request.urlopen(f"{API}/inn/session?player_id=p_demo01&format=block", timeout=10) as r:
        block = r.read().decode()
    if "MEMORY=无" in block:
        return False, "记忆写入后仍召回为空"
    line = [ln for ln in block.splitlines() if ln.startswith("MEMORY=")][0]
    return True, f"记忆召回生效：{line[:80]}…"


# ------------------------------------------------------------------ C5


REQUIRED_README = {
    "作品创意": ["创意", "玩法", "核心功能"],
    "体验方式": ["体验", "入口"],
    "技术分工": ["分工", "seekdb"],
    "运行环境": ["版本", "环境"],
    "安装步骤": ["步骤", "导入", "初始化"],
    "外部服务与网络": ["外部服务", "网络"],
    "已知限制": ["已知", "限制"],
}


def c5_readme():
    p = ROOT / "README.md"
    if not p.exists():
        return False, "README.md 不存在"
    text = p.read_text()
    missing = [k for k, kws in REQUIRED_README.items() if not any(kw in text for kw in kws)]
    if missing:
        return False, f"运行说明缺：{missing}"
    return True, f"六项要素齐全（{len(text)} 字）"


# ------------------------------------------------------------------ C6


SAMPLE_REQUIRED = ["初始", "输入", "预期", "证据"]


def c6_samples():
    d = ROOT / "samples"
    if not d.exists():
        return False, "samples/ 不存在"
    files = sorted(d.glob("S*.md"))
    if len(files) < 5:
        return False, f"样例只有 {len(files)} 个（需 ≥5）"
    bad = []
    for f in files:
        t = f.read_text()
        miss = [k for k in SAMPLE_REQUIRED if k not in t]
        if miss:
            bad.append(f"{f.name} 缺 {miss}")
    if bad:
        return False, "; ".join(bad)
    return True, f"{len(files)} 个样例，必需要素齐全"


# ------------------------------------------------------------------ C7


SECRET_RE = re.compile(r"sk-[A-Za-z0-9]{16,}")


def c7_no_secrets():
    hits = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".yml", ".yaml", ".md", ".py", ".sh", ".sql", ".json", ".txt", ".env"}:
            continue
        if ".venv" in p.parts or "__pycache__" in p.parts:
            continue
        try:
            t = p.read_text(errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        if SECRET_RE.search(t):
            hits.append(str(p.relative_to(ROOT)))
    if hits:
        return False, f"疑似真实凭证：{hits[:5]}"
    return True, "未发现 sk- 形式的真实凭证"


# ------------------------------------------------------------------ C8


def c8_evidence():
    idx = ROOT / "evidence" / "README.md"
    if not idx.exists():
        return False, "evidence/README.md 缺失"
    text = idx.read_text()
    refs = [r for r in re.findall(r"\]\(([^)]+)\)", text) if not r.startswith(("http", "#"))]
    missing = [r for r in refs if not (idx.parent / r).resolve().exists()]
    if missing:
        return False, f"索引指向的文件缺失：{missing[:4]}"
    return True, f"索引 {len(refs)} 条，全部存在"


# ------------------------------------------------------------------ main


def main() -> int:
    check("C1", "DSL 可重导入", c1_dsl_importable)
    check("C2", "seekdb 承载数据", c2_seekdb_data)
    check("C3", "seekdb 检索生效", c3_hybrid_retrieval)
    check("C4", "Dify 应用可运行", c4_app_runs)
    check("C9", "PowerContext 记忆生效", c9_powercontext)
    check("C5", "运行说明完整", c5_readme)
    check("C6", "验证样例完整", c6_samples)
    check("C7", "无真实凭证", c7_no_secrets)
    check("C8", "证据索引有效", c8_evidence)

    passed = sum(1 for _, ok, _ in results if ok)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"## 合规自检 {now}", "", f"通过 {passed}/{len(results)}", ""]
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        lines.append(f"- [{mark}] **{name}** — {detail}")
    report = "\n".join(lines)
    print(report)

    if "--log" in sys.argv:
        log = ROOT / "docs" / "progress-log.md"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write("\n" + report + "\n")
        print(f"\n[log] 已追加到 {log}")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
