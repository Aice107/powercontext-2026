"""pylibseekdb 的 Cursor.execute 只接受一个字符串参数，没有参数绑定。

所有 SQL 字面量必须在这里统一转义。规则与 MySQL 默认模式一致：
反斜杠优先转义，然后单引号；控制字符按 \\x 形式给出。
只用于把用户输入放进单引号字符串字面量，标识符永远来自代码内的白名单。
"""

from __future__ import annotations

_ESCAPES = {
    "\\": "\\\\",
    "'": "\\'",
    '"': '\\"',
    "\0": "\\0",
    "\n": "\\n",
    "\r": "\\r",
    "\x1a": "\\Z",
    "\b": "\\b",
    "\t": "\\t",
}


def sql_str(value: object) -> str:
    """把任意值编码成可安全嵌入单引号字面量的字符串。"""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    out: list[str] = []
    for ch in text:
        out.append(_ESCAPES.get(ch, ch))
    return "'" + "".join(out) + "'"


def sql_ident(name: str) -> str:
    """反引号包裹标识符。只允许来自代码白名单的名字，这里做防御性校验。"""
    import re

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or ""):
        raise ValueError(f"非法标识符: {name!r}")
    return f"`{name}`"
