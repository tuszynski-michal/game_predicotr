"""One real Windows checkout proves raw auditor hashes survive autocrlf."""

import hashlib
import json
import subprocess
from pathlib import Path


def test_audit_receipt_raw_sha_survives_fresh_autocrlf_checkout(tmp_path):
    root = Path(__file__).resolve().parents[2]
    relative = "ai_docs/quality/TASK-1172_AUDIT_claude-opus-5-5.md"
    source = root / relative
    before = source.read_bytes()
    receipt = json.loads(source.with_suffix(".receipt.json").read_bytes())
    assert hashlib.sha256(before).hexdigest() == receipt["report_sha256"]
    prefix = tmp_path.as_posix() + "/"
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=true",
            "-c",
            "core.eol=crlf",
            "checkout-index",
            "--prefix=" + prefix,
            "--",
            relative,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        timeout=20,
    )
    checkout = (tmp_path / relative).read_bytes()
    assert b"\r\n" not in checkout
    assert hashlib.sha256(checkout).hexdigest() == receipt["report_sha256"]
    assert source.read_bytes() == before
