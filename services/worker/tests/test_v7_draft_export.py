import hashlib
import json

import pytest
from game_predictor_worker.semi_automatic_selection.contracts import SemiAutomaticSelectionSource
from game_predictor_worker.semi_automatic_selection.v7_draft_export import publish_draft


def test_publish_retry_and_lost_sidecar(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    content = b"existing source bytes"
    (root / "photo.jpg").write_bytes(content)
    source = SemiAutomaticSelectionSource(
        0, "photo.jpg", len(content), hashlib.sha256(content).hexdigest()
    )
    target = tmp_path / "results"
    assert publish_draft(root, target, source, start=1, end=9, metadata={"state": "inferred"})
    assert not publish_draft(root, target, source, start=1, end=9, metadata={"state": "inferred"})
    (target / "seq_1-9.jpg.json").unlink()
    assert not publish_draft(root, target, source, start=1, end=9, metadata={"state": "inferred"})
    assert json.loads((target / "seq_1-9.jpg.json").read_text())["approved"] is False
    (target / "seq_1-9.jpg").write_bytes(b"operator replacement")
    with pytest.raises(ValueError, match="file conflict"):
        publish_draft(root, target, source, start=1, end=9, metadata={"state": "inferred"})
    assert (target / "seq_1-9.jpg").read_bytes() == b"operator replacement"
