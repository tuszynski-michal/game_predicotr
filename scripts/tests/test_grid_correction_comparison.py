"""Report provenance and static interaction tests; no inference or domain writes."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "render_grid_correction_comparison.py"
spec = importlib.util.spec_from_file_location("comparison", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load report renderer: {SCRIPT}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ComparisonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.nodes = [[100 + col * 20, 100 + row * 20] for row in range(4) for col in range(6)]
        self.write(
            "inputs.json",
            {
                "photos": [
                    {
                        "id": "source",
                        "checksum_sha256": "sha",
                        "oriented_width": 1200,
                        "oriented_height": 900,
                    }
                ],
                "membership": [],
                "boards": [
                    {
                        "source_image_id": "source",
                        "position_index": 0,
                        "sequence_number": 10,
                        "id": "board",
                        "grid_rows": 3,
                        "grid_columns": 5,
                        "board_geometry": {"latticeNodes": self.nodes},
                    }
                ],
            },
        )
        self.write("learning-final.json", {"candidateVersionId": "new", "gameId": "game"})
        metrics = {"boards_correct": 1, "boards_expected": 1, "normalized_error": 0.01}
        role = {"photos": 1, "base": metrics, "candidate": metrics}
        self.write(
            "evaluation-final.json",
            {
                "versionId": "new",
                "baseVersionId": "old",
                "trainingGameId": "game",
                "status": "completed",
                "report": {
                    "verdict": "PASS",
                    "games": [
                        {
                            "gameId": "game",
                            "reasons": [],
                            "roles": {"VALIDATION": role, "REGRESSION": role},
                        }
                    ],
                },
            },
        )
        for directory, version in [("base", "old"), ("candidate", "new")]:
            self.write(
                f"{directory}/source.json",
                {
                    "versionId": version,
                    "sourceChecksum": "sha",
                    "status": "ok",
                    "detections": [{"nodes": self.nodes}] * 9,
                },
            )
        (self.root / "photos").mkdir()
        (self.root / "photos/source.jpg").write_bytes(b"image-path-fixture")

    def write(self, name: str, data: object) -> None:
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data), encoding="utf-8")

    def test_modes_keep_geometry_and_provenance(self) -> None:
        output = module.render(self.root)
        html = output.read_text(encoding="utf-8")
        self.assertIn("brak potwierdzenia w zapisanym zestawie", html)
        self.assertNotIn("__DATA__", html)
        cards = json.loads((self.root / "comparison-data.json").read_text())
        self.assertEqual(cards[0]["saved"], self.nodes)
        result = subprocess.run(
            [
                "node",
                str(SCRIPT.parent / "tests/verify_grid_correction_comparison.mjs"),
                str(output),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mismatched_models_and_checksums_are_rejected(self) -> None:
        for field, value in [("sourceChecksum", "wrong"), ("versionId", "wrong")]:
            with self.subTest(field=field):
                original = json.loads((self.root / "candidate/source.json").read_text())
                wrong = {**original, field: value}
                self.write("candidate/source.json", wrong)
                with self.assertRaises(ValueError):
                    module.render(self.root)
                self.write("candidate/source.json", original)

    def test_application_requires_completed_matching_receipts(self) -> None:
        steps: list[dict[str, object]] = [
            {
                "kind": kind,
                "gameId": "game" if kind == "activate" else None,
                "status": "completed",
                "receipt": {"versionId": "new"},
            }
            for kind in ["publish", "set_default", "activate"]
        ]
        operation = {"status": "completed", "versionId": "new", "gameId": "game", "steps": steps}
        self.write("apply-final.json", {"operation": operation})
        self.assertIn(
            "zapisana operacja potwierdza", module.render(self.root).read_text(encoding="utf-8")
        )
        steps[-1]["status"] = "failed"
        self.write("apply-final.json", {"operation": operation})
        self.assertIn(
            "brak potwierdzenia w zapisanym zestawie",
            module.render(self.root).read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
