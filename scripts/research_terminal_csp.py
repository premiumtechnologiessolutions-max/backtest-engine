"""Pin the Quant Terminal's sole inline controller to an offline CSP hash.

This operates on final escaped HTML, so the browser accepts only the exact
bundled script bytes. It does not certify any backtest or data provenance.
"""
from __future__ import annotations

import base64
import hashlib
import re

SCRIPT_OPEN = re.compile(r"<script\b[^>]*>", re.IGNORECASE)
SCRIPT_CLOSE = re.compile(r"</script\s*>", re.IGNORECASE)
SCRIPT_BLOCK = re.compile(r"<script>(.*?)</script>", re.DOTALL)


def lock_offline_script(html: str) -> str:
    """Add a CSP allowing exactly the bundled script; reject extra scripts.

    Inline CSS remains allowed for the terminal's fixed stylesheet and
    per-family bounded progress widths. Network fetches are blocked by CSP;
    intentional evidence-link navigation remains available.
    """
    if (type(html) is not str or html.count("<head>") != 1
            or html.count("</head>") != 1
            or 'http-equiv="Content-Security-Policy"' in html):
        raise ValueError("Malformed or already policy-wrapped terminal HTML")
    opens = SCRIPT_OPEN.findall(html)
    closes = SCRIPT_CLOSE.findall(html)
    block = SCRIPT_BLOCK.search(html)
    if (opens != ["<script>"] or closes != ["</script>"]
            or block is None or not block.group(1).strip()):
        raise ValueError("Terminal must have one nonempty bundled inline script")
    digest = base64.b64encode(hashlib.sha256(block.group(1).encode("utf-8")).digest()).decode("ascii")
    policy = (
        "default-src 'none'; base-uri 'none'; object-src 'none'; "
        "connect-src 'none'; img-src 'none'; font-src 'none'; "
        "media-src 'none'; frame-src 'none'; worker-src 'none'; "
        "form-action 'none'; style-src 'unsafe-inline'; "
        "script-src 'sha256-" + digest + "'; script-src-attr 'none'"
    )
    return html.replace(
        "<head>",
        '<head><meta http-equiv="Content-Security-Policy" content="' + policy + '">',
        1,
    )
