"""编码回退链与换行归一（TRAP-01：GB18030 与 UTF-8 混用不能直接崩）。"""

from __future__ import annotations

from app import config
from app.errors import DomainError

BOM = "\ufeff"


def decode_bytes(raw: bytes) -> tuple[str, list[str]]:
    """按 config.ENCODINGS 顺序回退解码，返回文本与文件级诊断码。"""
    codes: list[str] = []
    if raw.startswith(b"\xef\xbb\xbf"):
        codes.append("BOM_STRIPPED")
    for encoding in config.ENCODINGS:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if encoding == "gb18030":
            codes.append("ENCODING_FALLBACK")
        if text.startswith(BOM):
            text = text.lstrip(BOM)
        return text, codes
    raise DomainError("ENCODING_FAILED", "按回退链仍无法解码输入文件", 422)


def normalize_newlines(text: str) -> str:
    """CRLF 与 CR 统一成 LF，逻辑行数才等于记录数。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")
