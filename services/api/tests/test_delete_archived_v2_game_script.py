from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import UUID


def _load_script() -> ModuleType:
    path = Path(__file__).parents[3] / "scripts" / "delete_archived_v2_game.py"
    spec = importlib.util.spec_from_file_location("delete_archived_v2_game", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()
GAME_ID = UUID("11111111-1111-4111-8111-111111111111")


def _location(**overrides: object) -> dict[str, object]:
    return {
        "storeSchema": script.SCHEMA,
        "generation": 2,
        "manifestVersion": script.VERSION,
        "status": "active",
        **overrides,
    }


def _blocker_codes(**overrides: object) -> list[str]:
    arguments: dict[str, object] = {
        "game_status": "archived",
        "location": _location(),
        "active_job_count": 0,
        "mobile_release_rows": 0,
        "uncovered_references": [],
        **overrides,
    }
    return [str(blocker["code"]) for blocker in script.collect_blockers(**arguments)]


def test_archived_v2_game_without_references_has_no_blockers() -> None:
    assert _blocker_codes() == []
    assert _blocker_codes(location=_location(status="deleting")) == []


def test_non_archived_game_is_blocked() -> None:
    assert _blocker_codes(game_status="draft") == ["GAME_NOT_ARCHIVED"]
    assert _blocker_codes(game_status="active") == ["GAME_NOT_ARCHIVED"]


def test_invalid_storage_location_is_blocked() -> None:
    expected = ["GAME_STORAGE_LOCATION_INVALID"]
    assert _blocker_codes(location=None) == expected
    assert _blocker_codes(location=_location(storeSchema="public")) == expected
    assert _blocker_codes(location=_location(manifestVersion="other")) == expected
    assert _blocker_codes(location=_location(status="migrating")) == expected


def test_active_jobs_release_membership_and_foreign_rows_are_blocked() -> None:
    assert _blocker_codes(
        active_job_count=1,
        mobile_release_rows=2,
        uncovered_references=[{"table": "board_search_share_sessions", "rows": 3}],
    ) == ["GAME_HAS_ACTIVE_JOBS", "GAME_IN_MOBILE_RELEASE", "GAME_HAS_UNCOVERED_REFERENCES"]


def test_confirmation_names_the_exact_game() -> None:
    assert script.confirmation_phrase("mums", GAME_ID) == f"DELETE GAME mums {GAME_ID}"


def test_preview_digest_ignores_itself_and_tracks_content() -> None:
    preview: dict[str, object] = {"game": {"id": str(GAME_ID)}, "partitions": {"rows": 1}}
    digest = script.preview_digest(preview)
    assert script.preview_digest({**preview, "previewSha256": digest}) == digest
    assert script.preview_digest({**preview, "partitions": {"rows": 2}}) != digest


def test_management_history_restrict_references_block_before_deletion(monkeypatch, capsys) -> None:
    """The dynamic preflight covers retained management rows before any partition drop."""

    class Result:
        def __init__(self, value):
            self.value = value

        def all(self):
            return self.value

        def scalar_one(self):
            return self.value

    class ReadOnlySession:
        def __init__(self, _engine):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def execute(self, statement, parameters):
            sql = str(statement)
            assert parameters.get("game_id", GAME_ID) == GAME_ID
            if "FROM pg_constraint" in sql:
                assert "fk.confdeltype <> 'c'" in sql
                return Result(
                    [
                        ("management_assignments", "games", "assignment_game_fk", 1, "game_id"),
                        ("management_result_versions", "games", "result_game_fk", 1, "game_id"),
                        ("management_journal", "games", "journal_game_fk", 1, "game_id"),
                    ]
                )
            assert sql.startswith('SELECT count(*) FROM public."management_')
            return Result(1)

    references = script._uncovered_references(ReadOnlySession(None), GAME_ID)
    assert {reference["table"] for reference in references} == {
        "management_assignments",
        "management_result_versions",
        "management_journal",
    }
    blockers = script.collect_blockers(
        game_status="archived",
        location=_location(),
        active_job_count=0,
        mobile_release_rows=0,
        uncovered_references=references,
    )
    calls = []
    monkeypatch.setattr(script, "Session", ReadOnlySession)
    monkeypatch.setattr(script, "_engine", lambda **kwargs: calls.append(kwargs) or object())
    monkeypatch.setattr(
        script,
        "build_preview",
        lambda *_args: {
            "blockers": blockers,
            "confirmation": "confirmed",
            "previewSha256": "digest",
        },
    )
    monkeypatch.setattr(script, "_has_running_delete", lambda *_args: False)
    monkeypatch.setattr(script, "execute_deletion", lambda *_args: calls.append("delete"))
    assert (
        script.main(
            [
                "--game-id",
                str(GAME_ID),
                "--execute",
                "--confirmation",
                "confirmed",
                "--expected-preview-sha256",
                "digest",
            ]
        )
        == 1
    )
    assert calls == [{"read_only": True}]
    assert "GAME_DELETION_BLOCKED" in capsys.readouterr().out
