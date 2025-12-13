from __future__ import annotations
import re
from typing import Dict

_SIG_RE = re.compile(r"(^--\s*$.*)|(^Sent from my.*$)", re.IGNORECASE | re.MULTILINE)

def strip_signature(text: str) -> str:
    # Very conservative: remove common separators and mobile signatures
    t = text.strip()
    t = _SIG_RE.sub("", t).strip()
    return t

def safe_fill_template(template: str, mapping: Dict[str, str]) -> str:
    # Simple {{KEY}} replacement
    out = template
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)
    return out
