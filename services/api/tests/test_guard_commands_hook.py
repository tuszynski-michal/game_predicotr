from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPOSITORY_ROOT / "scripts" / "hooks" / "guard_commands.py"
OLD = r"C:\Users\tuszy\Documents\game_predicotr"
OLD_BASH = "/c/Users/tuszy/Documents/game_predicotr"


def _run(payload: object | str) -> tuple[int, str, str]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    env = {key: value for key, value in os.environ.items() if key != "CLAUDE_PROJECT_DIR"}
    result = subprocess.run(
        [sys.executable, "-I", str(HOOK)],
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        env=env,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _command(tool: str, command: str, **extra: object) -> dict[str, object]:
    return {"tool_name": tool, "tool_input": {"command": command}, **extra}


def _asks(tool: str, command: str, **extra: object) -> str:
    code, stdout, stderr = _run(_command(tool, command, **extra))
    assert (code, stderr) == (0, ""), command
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "ask", command
    assert "wymaga potwierdzenia" in decision["permissionDecisionReason"]
    return str(decision["permissionDecisionReason"])


def _allows(tool: str, command: str, **extra: object) -> None:
    assert _run(_command(tool, command, **extra)) == (0, "", ""), command


@pytest.mark.parametrize(
    ("tool", "command"),
    [
        ("PowerShell", "npm run db:reset:local"),
        ("Bash", "npm run db:reset:local --workspace x"),
        ("PowerShell", "git push --force origin main"),
        ("PowerShell", "git push -f origin main"),
        ("Bash", "git push origin main --force-with-lease"),
        ("Bash", "git push --force-with-lease=main:abc origin main"),
        ("Bash", "git push -fu origin feat/x"),
        ("Bash", "git push origin +main"),
        ("Bash", "git -C D:/game_predicotr push -f origin main"),
        ("Bash", "cd /d/game_predicotr && git push --force origin x"),
        ("PowerShell", "git reset --hard HEAD~1"),
        ("Bash", "git reset --hard"),
        ("Bash", "git clean -fd"),
        ("PowerShell", "git clean -xdf"),
        ("Bash", "git clean --force -d"),
        ("Bash", "git worktree remove --force worktrees/x"),
        ("PowerShell", "git worktree remove -f worktrees/x"),
        ("Bash", "git worktree remove worktrees/x --force"),
        ("Bash", "git branch -D feat/x"),
        ("PowerShell", 'psql -c "DROP DATABASE game_predictor_test"'),
        ("Bash", "psql -c 'drop table jobs;'"),
        ("Bash", 'psql -c "Drop Schema public CASCADE"'),
        ("Bash", "psql -c 'TRUNCATE TABLE jobs'"),
        ("Bash", "psql -c 'truncate jobs;'"),
        ("PowerShell", "Remove-Item -Recurse -Force D:\\game_predicotr"),
        ("PowerShell", "Remove-Item D:\\game_predicotr\\ -Recurse"),
        ("PowerShell", "Remove-Item -Path D:\\game_predicotr\\.venv -Recurse -Force"),
        ("PowerShell", "Remove-Item -LiteralPath D:\\game_predicotr\\node_modules -Recurse"),
        ("PowerShell", "rm -r -fo D:\\game_predicotr\\worktrees\\x\\node_modules"),
        ("PowerShell", "Remove-Item apps\\admin\\node_modules\\.cache -Recurse"),
        ("Bash", "rm -rf /d/game_predicotr"),
        ("Bash", "rm -rf D:/game_predicotr/.venv"),
        ("Bash", "rm -rf node_modules"),
        ("Bash", "rm -fr ./node_modules/"),
        ("Bash", "rm -R .venv"),
        ("Bash", "rm --recursive --force worktrees/x/.venv"),
        ("Bash", "cmd /c rmdir /s /q D:\\game_predicotr\\worktrees\\x\\node_modules"),
        ("PowerShell", "cmd /c rd /s /q D:\\game_predicotr"),
        ("PowerShell", 'powershell -Command "Remove-Item .venv -Recurse -Force"'),
        ("Bash", f"rm -rf {REPOSITORY_ROOT.as_posix()}"),
        ("Bash", f"rm -rf {REPOSITORY_ROOT.as_posix()}/*"),
        ("Bash", f"git -C {OLD} commit -m x"),
        ("PowerShell", f"git -C {OLD} push origin main"),
        ("PowerShell", f'git -C "{OLD}" reset --hard'),
        ("Bash", f"git -C {OLD_BASH} checkout main"),
        ("PowerShell", f"cd {OLD}; git commit -am x"),
        ("PowerShell", f"Set-Location {OLD}\ngit stash"),
        ("Bash", f"cd {OLD_BASH} && git merge feat/x"),
        ("Bash", f"git --git-dir={OLD}\\.git add ."),
        ("PowerShell", f"Set-Content -Path {OLD}\\README.md -Value x"),
        ("PowerShell", f"'x' | Out-File {OLD}\\notes.txt"),
        ("PowerShell", f"Add-Content {OLD}\\notes.txt 'x'"),
        ("PowerShell", f"Remove-Item {OLD}\\scratch.txt"),
        ("PowerShell", f"Move-Item {OLD}\\a.txt D:\\game_predicotr\\a.txt"),
        ("PowerShell", f"Copy-Item D:\\game_predicotr\\a.txt {OLD}\\a.txt"),
        ("PowerShell", f"Copy-Item D:\\game_predicotr\\a.txt -Destination {OLD}\\a.txt"),
        ("Bash", f"echo x > {OLD_BASH}/notes.txt"),
    ],
)
def test_destructive_commands_ask(tool: str, command: str) -> None:
    _asks(tool, command)


@pytest.mark.parametrize(
    ("tool", "command"),
    [
        ("PowerShell", "git push origin main"),
        ("Bash", "git push -u origin feat/claude-automations"),
        ("Bash", "git push --follow-tags origin main"),
        ("Bash", "git branch -d feat/x"),
        ("Bash", "git branch --show-current"),
        ("PowerShell", "git reset --soft HEAD~1"),
        ("PowerShell", "git reset HEAD file.txt"),
        ("Bash", "git clean -n -d"),
        ("Bash", "git worktree remove worktrees/x"),
        ("Bash", "git worktree add worktrees/x -b feat/x main"),
        ("Bash", "git commit -m 'fix -f flag handling'"),
        ("Bash", "echo git push --force"),
        ("PowerShell", "cmd /c rmdir D:\\game_predicotr\\worktrees\\x\\node_modules"),
        ("PowerShell", "cmd /c rmdir D:\\game_predicotr\\worktrees\\x\\.venv"),
        ("PowerShell", "npm run docs:check"),
        ("PowerShell", "npm run db:up; npm run db:migrate"),
        ("Bash", "npm run lint --workspace @game-predictor/admin"),
        ("PowerShell", "Remove-Item scratch.txt"),
        ("PowerShell", "Remove-Item D:\\game_predicotr\\.test-tmp\\scratch.txt -Force"),
        ("PowerShell", "Remove-Item D:\\pta1 -Recurse -Force"),
        ("Bash", "rm -rf /tmp/scratch"),
        ("Bash", "rm -f build/out.txt"),
        ("PowerShell", "Remove-Item D:\\game_predicotr\\worktrees\\x\\.next -Recurse"),
        ("Bash", "rm -rf apps/admin/.next"),
        ("Bash", "ls node_modules"),
        ("PowerShell", "Get-ChildItem .venv -Recurse | Measure-Object"),
        ("Bash", "psql -c 'SELECT count(*) FROM jobs'"),
        ("Bash", "psql -c 'DELETE FROM scratch_table'"),
        ("PowerShell", "git log --grep truncate output"),
        ("PowerShell", f"git -C {OLD} status"),
        ("Bash", f"git -C {OLD_BASH} log --oneline -5"),
        ("Bash", f"git -C {OLD} show HEAD:README.md"),
        ("PowerShell", f"cd {OLD}; git status; git diff"),
        ("PowerShell", f"Get-Content {OLD}\\README.md"),
        ("PowerShell", f"Copy-Item {OLD}\\a.txt D:\\game_predicotr\\a.txt"),
        ("PowerShell", f"Copy-Item -Path {OLD}\\a.txt -Destination D:\\game_predicotr\\a.txt"),
        ("PowerShell", f"Select-String -Path {OLD}\\*.md -Pattern x"),
        ("Bash", f"cat {OLD_BASH}/README.md > /tmp/readme.txt"),
        ("Bash", "git -C D:/game_predicotr/worktrees/x commit -m 'v1.7.386 - x'"),
    ],
)
def test_ordinary_commands_are_allowed(tool: str, command: str) -> None:
    _allows(tool, command)


def test_relative_recursive_delete_is_resolved_against_cwd() -> None:
    _asks("Bash", "rm -rf *", cwd="D:\\game_predicotr")
    _asks("PowerShell", "Remove-Item . -Recurse -Force", cwd=str(REPOSITORY_ROOT))
    _asks("Bash", "rm -rf ../..", cwd="D:\\game_predicotr\\worktrees\\x")
    _allows("Bash", "rm -rf *", cwd="D:\\game_predicotr\\.test-tmp\\scratch")
    _allows("Bash", "rm -rf out", cwd="D:\\game_predicotr")


def test_reason_names_every_matched_pattern() -> None:
    reason = _asks("Bash", "git push -f origin main && git reset --hard && rm -rf node_modules")
    assert "git push" in reason
    assert "git reset --hard" in reason
    assert "node_modules" in reason


def test_decision_json_is_ascii_safe() -> None:
    _, stdout, _ = _run(_command("Bash", "git clean -fd"))
    assert stdout.isascii()
    assert "nie\\u015bledzone" in stdout


def test_other_tools_and_garbage_fail_open() -> None:
    assert _run(_command("Read", "git push --force")) == (0, "", "")
    assert _run({"tool_name": "Edit", "tool_input": {"file_path": "x"}}) == (0, "", "")
    assert _run("not json") == (0, "", "")
    assert _run("[]") == (0, "", "")
    assert _run("") == (0, "", "")
    assert _run({"tool_name": "Bash", "tool_input": "git push -f"}) == (0, "", "")
    assert _run({"tool_name": "Bash", "tool_input": {}}) == (0, "", "")
    assert _run({"tool_name": "Bash", "tool_input": {"command": 5}}) == (0, "", "")
    assert _run({"tool_name": "Bash", "tool_input": {"command": "   "}}) == (0, "", "")
    assert _run({"tool_name": "Bash"}) == (0, "", "")
