"""Running Claude through the Claude Code CLI, on the listener's claude.ai subscription.

Tested from Kodi 21's Python on Windows (docs/concept_ai_mix_assist.md, "Running Claude from Kodi"):
- the CLI runs without a console window when started with CREATE_NO_WINDOW;
- Kodi's environment may contain ANTHROPIC_API_KEY, which would make the CLI bill an API account instead of the
  subscription, so it is removed for every call;
- the CLI may only exist inside an editor extension whose folder name contains its version.
"""

from __future__ import annotations

import glob
import itertools
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from mixassist import trace, usage

CREATE_NO_WINDOW = 0x08000000

# Credentials that would make the CLI use an API account instead of the subscription.
API_CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"
DEFAULT_TIMEOUT = 600

# Why a call failed, for messages to the listener.
NOT_FOUND = "not_found"
NOT_LOGGED_IN = "not_logged_in"
USAGE_LIMIT = "usage_limit"
TIMEOUT = "timeout"
FAILED = "failed"

REQUEST_NUMBERS = itertools.count(1)


class ClaudeError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def extension_version(path: str) -> Tuple[int, int, int]:
    match = re.search(r"claude-code-(\d+)\.(\d+)\.(\d+)", path)
    return tuple(int(part) for part in match.groups()) if match else (0, 0, 0)


def cli_candidates(home: str = "", appdata: str = "", which: Callable[[str], Optional[str]] = shutil.which) -> List[str]:
    """Where the CLI may be, most stable first: a standalone install, the PATH, npm, then editor extensions
    (newest version first)."""
    home = home or os.path.expanduser("~")
    appdata = appdata if appdata is not None and appdata != "" else os.environ.get("APPDATA", "")
    found: List[str] = []
    for path in (os.path.join(home, ".local", "bin", "claude.exe"), os.path.join(home, ".local", "bin", "claude")):
        if os.path.isfile(path):
            found.append(path)
    on_path = which("claude")
    if on_path:
        found.append(on_path)
    if appdata:
        npm = os.path.join(appdata, "npm", "claude.cmd")
        if os.path.isfile(npm):
            found.append(npm)
    for editor in (".vscode", ".vscode-insiders", ".cursor", ".windsurf"):
        pattern = os.path.join(home, editor, "extensions", "anthropic.claude-code-*", "resources", "native-binary", "claude*")
        found += sorted((path for path in glob.glob(pattern) if os.path.isfile(path)), key=extension_version, reverse=True)
    unique: List[str] = []
    for path in found:
        if path not in unique:
            unique.append(path)
    return unique


def find_cli(configured: str = "", **kwargs) -> str:
    """The configured path if it exists, otherwise the first candidate; "" if there is none."""
    if configured and os.path.isfile(configured):
        return configured
    candidates = cli_candidates(**kwargs)
    return candidates[0] if candidates else ""


def cli_environment(base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    environment = dict(os.environ if base is None else base)
    for name in API_CREDENTIALS:
        environment.pop(name, None)
    return environment


def run_command(cli: str, args: Sequence[str], stdin_text: str = "", timeout: int = DEFAULT_TIMEOUT,
                runner: Callable = subprocess.run) -> Tuple[str, str]:
    """Run the CLI quietly (no console window) without API credentials; returns stdout and stderr."""
    workdir = tempfile.mkdtemp(prefix="mixassist_")
    try:
        completed = runner(
            [cli] + list(args), input=stdin_text, capture_output=True, text=True, encoding="utf-8",
            env=cli_environment(), cwd=workdir, timeout=timeout,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired:
        raise ClaudeError(TIMEOUT, "Claude did not answer in time.")
    except OSError as exc:
        raise ClaudeError(NOT_FOUND, f"The Claude CLI could not be started: {exc}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return completed.stdout or "", completed.stderr or ""


def structured_command(system_prompt: str, schema: dict, model: str = DEFAULT_MODEL,
                       effort: str = DEFAULT_EFFORT) -> List[str]:
    """Print mode with a replaced system prompt, structured output and no tools.

    Never --bare: it accepts only API-key authentication, so it would bypass the subscription."""
    return [
        "-p", "--output-format", "json", "--model", model, "--effort", effort,
        "--system-prompt", system_prompt, "--json-schema", json.dumps(schema),
        "--tools", "", "--no-session-persistence",
    ]


def classify_failure(text: str, status: Optional[int] = None) -> str:
    lowered = (text or "").lower()
    if status == 429 or ("limit" in lowered and any(word in lowered for word in ("usage", "reached", "hit your"))):
        return USAGE_LIMIT
    if status == 401 or any(word in lowered for word in ("not logged in", "/login", "please log in", "authentication")):
        return NOT_LOGGED_IN
    return FAILED


def parse_structured(stdout: str, stderr: str = "") -> dict:
    """The structured output of a print-mode call; raises ClaudeError with the reason if there is none."""
    try:
        payload = json.loads(stdout)
    except ValueError:
        text = (stdout.strip() or stderr.strip())[:300]
        raise ClaudeError(classify_failure(text), f"Claude returned no result: {text}")
    if payload.get("is_error") or payload.get("subtype") != "success":
        text = str(payload.get("result", ""))[:300]
        raise ClaudeError(classify_failure(text, payload.get("api_error_status")), f"Claude reported an error: {text}")
    structured = payload.get("structured_output")
    if structured is None:
        try:
            structured = json.loads(str(payload.get("result", "")))
        except ValueError:
            raise ClaudeError(FAILED, "Claude's answer was not in the expected format.")
    return structured


def call_usage(stdout: str) -> dict:
    """What a print-mode call reports about itself: tokens, the equivalent API cost (not billed on a
    subscription) and Claude's own time; {} when the answer isn't readable."""
    try:
        payload = json.loads(stdout)
    except ValueError:
        return {}
    if not isinstance(payload, dict):
        return {}
    tokens = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return {
        "input_tokens": int(tokens.get("input_tokens") or 0),
        "output_tokens": int(tokens.get("output_tokens") or 0),
        "cache_read_tokens": int(tokens.get("cache_read_input_tokens") or 0),
        "cache_write_tokens": int(tokens.get("cache_creation_input_tokens") or 0),
        "cost_usd": float(payload.get("total_cost_usd") or 0),
    }


def ask(cli: str, system_prompt: str, schema: dict, message: str, model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT, timeout: int = DEFAULT_TIMEOUT, runner: Callable = subprocess.run) -> dict:
    """One structured request; returns the parsed structured output. Each request is reported (usage.emit
    "ai_call"): its system prompt (the add-on tells the purpose from it), whether it worked, tokens and time."""
    if not cli:
        raise ClaudeError(NOT_FOUND, "The Claude CLI was not found.")
    started = time.monotonic()
    report = {"system_prompt": system_prompt, "model": model, "ok": False}
    request = next(REQUEST_NUMBERS)  # pairs a request with its answer in the log
    if trace.active():  # only then: prompt_label() remembers which prompts the log has in full
        trace.say(f"AI request {request} ({model}, effort {effort}), {trace.prompt_label(system_prompt)}\n"
                  f"Message:\n{message}")
    stderr = ""
    try:
        stdout, stderr = run_command(cli, structured_command(system_prompt, schema, model, effort), message, timeout,
                                     runner)
        report.update(call_usage(stdout))
        result = parse_structured(stdout, stderr)
        report["ok"] = True
        if trace.active():
            trace.say(f"AI answer {request}:\n{json.dumps(result, ensure_ascii=False, indent=1)}")
        return result
    except ClaudeError as exc:
        report["failure"] = exc.kind
        trace.say(f"AI request {request} failed ({exc.kind}): {exc}" + (f"\nstderr: {stderr.strip()[:2000]}"
                                                                        if stderr.strip() else ""))
        raise
    finally:
        report["seconds"] = round(time.monotonic() - started, 1)
        trace.say(f"AI request {request}: {report['seconds']} s, tokens in {report.get('input_tokens', 0)} "
                  f"(cache read {report.get('cache_read_tokens', 0)}, written {report.get('cache_write_tokens', 0)}), "
                  f"out {report.get('output_tokens', 0)}, API-equivalent cost ${report.get('cost_usd', 0):.4f}.")
        usage.emit("ai_call", **report)


def check(cli: str, runner: Callable = subprocess.run) -> dict:
    """Whether the CLI runs and is logged in to a subscription. Only yes/no is kept: the login status
    includes the account's e-mail address, which must not end up in logs."""
    result = {"found": bool(cli), "version": "", "logged_in": False, "subscription": False}
    if not cli:
        return result
    try:
        stdout, _ = run_command(cli, ["--version"], timeout=60, runner=runner)
        result["version"] = stdout.strip().split(" ")[0]
        stdout, _ = run_command(cli, ["auth", "status"], timeout=60, runner=runner)
    except ClaudeError:
        result["found"] = False
        return result
    try:
        status = json.loads(stdout)
    except ValueError:
        return result
    result["logged_in"] = bool(status.get("loggedIn"))
    result["subscription"] = status.get("authMethod") == "claude.ai"
    return result
