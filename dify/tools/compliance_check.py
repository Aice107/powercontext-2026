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


def _refresh_login() -> bool:
    """Dify 控制台令牌 60 分钟过期：命中 401 时调 tools/dify-login.sh 重新登录一次。"""
    script = Path(__file__).resolve().parent / "dify-login.sh"
    if not script.is_file():
        return False
    r = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def http_json(url: str, data: dict | None = None, headers: dict | None = None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers or {})
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code != 401 or not _refresh_login():
            raise
        req.remove_header("Cookie")
        req.add_header("Cookie", cookie_header())
        req.add_header("X-CSRF-Token", csrf_token())
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
    # 先造一条"旧账"，再查相似事件：自检必须自带前置数据，不依赖演示玩家
    pid_c3 = "p_check_" + time.strftime("%Y%m%d%H")
    http_json(
        f"{API}/inn/ledger",
        {
            "player_id": pid_c3,
            "conversation_id": "chk_hybrid",
            "action_text": "往酒坛里兑了半坛井水",
            "action_type": "drink",
            "severity": 2,
            "scene": "后厨",
        },
    )
    payload = {
        "player_id": pid_c3,
        "conversation_id": "chk_hybrid",
        "action_text": "又往酒坛里兑水",
        "action_type": "drink",
        "severity": 1,
        "scene": "后厨",
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
    payload = {"inputs": {"player_id": "p_check_" + time.strftime("%Y%m%d%H")}, "files": [], "query": "往酒坛里兑半坛水"}
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

    def _open():
        req = urllib.request.Request(
            f"{DIFY}/console/api/apps/{APP_ID}/advanced-chat/workflows/draft/run",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Cookie": cookie_header(),
                "X-CSRF-Token": csrf_token(),
            },
        )
        return urllib.request.urlopen(req, timeout=180)

    try:
        resp = _open()
    except urllib.error.HTTPError as exc:
        if exc.code != 401 or not _refresh_login():
            raise
        resp = _open()
    with resp:
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
    # 自检玩家按小时轮换：否则每轮都往同一个玩家写事件，仇值会涨到 100 让人困惑
    pid = "p_check_pc_" + time.strftime("%Y%m%d%H")
    payload = {"player_id": pid, "action_text": "在醋坛子里洗手", "action_type": "hygiene",
               "severity": 1, "scene": "后厨"}
    http_json(f"{API}/inn/ledger", payload)
    with urllib.request.urlopen(f"{API}/inn/session?player_id={pid}&format=block", timeout=10) as r:
        block = r.read().decode()
    if "MEMORY=无" in block:
        return False, "记忆写入后仍召回为空"
    line = [ln for ln in block.splitlines() if ln.startswith("MEMORY=")][0]
    return True, f"记忆召回生效：{line[:80]}…"


# ------------------------------------------------------------------ C10


def c10_package():
    """打包完整性：把 dify/ 打成 zip 到临时目录，检查必需项在包内、敏感文件被排除。"""
    import tempfile
    import zipfile

    required = [
        "README.md",
        "dsl/01_inn_chatflow.yml",
        "dsl/README.md",
        "backend/app/main.py",
        "backend/requirements.txt",
        "db/01_schema.sql",
        "db/init.sh",
        "deploy/bootstrap.sh",
        "tools/compliance_check.py",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["bash", "tools/package.sh", tmp], cwd=ROOT, capture_output=True, timeout=180, check=False)
        zips = list(Path(tmp).glob("*.zip"))
        if not zips:
            return False, "打包脚本没有产出 zip"
        zf = zipfile.ZipFile(zips[0])
        names = set(zf.namelist())
        missing = [r for r in required if r not in names]
        leaks = [n for n in names if n.endswith((".env", ".local.env")) or "/.venv/" in n or "__pycache__" in n]
        if missing:
            return False, f"包内缺必需文件：{missing[:4]}"
        if leaks:
            return False, f"包内含敏感/临时文件：{leaks[:4]}"
        return True, f"zip 内 {len(names)} 个文件，必需项齐全、无 .env/.venv 泄漏"


# ------------------------------------------------------------------ C11


def c11_doc_consistency():
    """文档与实物一致性：README 里写的节点数/台词数/样例数要和实际对得上。"""
    import yaml

    problems = []

    # 1) 节点数：DSL 实际 vs README 与 dsl/README 里出现的 "N 节点/N 个节点"
    dsl_nodes = len((yaml.safe_load(DSL.read_text()) or {})["workflow"]["graph"]["nodes"])
    for f in (ROOT / "README.md", ROOT / "dsl" / "README.md"):
        text = f.read_text()
        for m in re.finditer(r"(\d+)\s*(?:个)?节点", text):
            if int(m.group(1)) != dsl_nodes:
                problems.append(f"{f.name} 写 {m.group(1)} 个节点，实际 {dsl_nodes}")

    # 2) 台词数：README 里 "`inn_line` N 条" 与库内一致
    try:
        real_lines = int(mysql("SELECT COUNT(*) FROM inn_line"))
        for m in re.finditer(r"`inn_line`\s*(\d+)\s*条", (ROOT / "README.md").read_text()):
            if int(m.group(1)) != real_lines:
                problems.append(f"README 写 inn_line {m.group(1)} 条，实际 {real_lines}")
    except Exception:  # noqa: BLE001
        pass

    # 3) 样例数：README §6 表格里的 S* 行数 vs samples/ 文件数
    sample_files = len(list((ROOT / "samples").glob("S*.md")))
    listed = len(re.findall(r"^\|\s*S\d+[a-z]?\s*\|", (ROOT / "README.md").read_text(), re.MULTILINE))
    if listed != sample_files:
        problems.append(f"README 列了 {listed} 组样例，samples/ 有 {sample_files} 个文件")

    if problems:
        return False, "；".join(problems[:4])
    return True, f"节点 {dsl_nodes}、样例 {sample_files} 与文档一致"


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
    check("C10", "打包完整性", c10_package)
    check("C11", "文档与实物一致", c11_doc_consistency)
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
    if "--json" in sys.argv:
        import json as _json
        print(_json.dumps(
            {
                "at": now,
                "passed": passed,
                "total": len(results),
                "items": [{"name": n, "ok": ok, "detail": d} for n, ok, d in results],
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print(report)

    if "--log" in sys.argv:
        # 自检明细写 raw 文件；progress-log.md 是人工维护的时间线，不被脚本污染
        log = ROOT / "docs" / "progress-log.raw.md"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write("\n" + report + "\n")
        print(f"\n[log] 已追加到 {log}")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
