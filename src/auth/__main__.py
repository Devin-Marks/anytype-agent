"""Command line interface for Anytype-Agent owned auth flows."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Sequence

from .codex import (
    PROVIDER_KEY,
    CodexLoginError,
    codex_auth_file,
    login_with_manual_redirect,
    read_provider_credentials,
    remove_provider_credentials,
)
from src.llm.providers import _codex_token_record

PROVIDER = PROVIDER_KEY


def _provider(value: str) -> str:
    if value != PROVIDER:
        raise argparse.ArgumentTypeError("only openai-codex is supported")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.auth", description="Anytype-Agent auth CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("login", "status", "logout"):
        cmd = sub.add_parser(command)
        cmd.add_argument("provider", type=_provider, help="auth provider (openai-codex)")
    return parser


async def _login() -> int:
    try:
        path = await login_with_manual_redirect()
    except (CodexLoginError, OSError) as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1
    print(f"Logged in to {PROVIDER}; credentials saved at {path}")
    return 0


def _status() -> int:
    path = codex_auth_file()
    try:
        data = read_provider_credentials(path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"{PROVIDER}: credential file is unreadable: {path} ({exc.__class__.__name__})")
        return 1
    if data is None:
        print(f"{PROVIDER}: not logged in ({path})")
        return 1
    _record, token, refresh, expiry = _codex_token_record(data)
    if not token:
        print(f"{PROVIDER}: credential file has no access token ({path})")
        return 1
    refresh_note = "refresh credential present" if refresh else "no refresh credential"
    expiry_note = f", expires {expiry.isoformat()}" if expiry else ""
    print(f"{PROVIDER}: logged in ({refresh_note}{expiry_note}) at {path}")
    return 0


def _logout() -> int:
    path = codex_auth_file()
    try:
        removed = remove_provider_credentials(path)
    except FileNotFoundError:
        removed = False
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Logout failed: {exc}", file=sys.stderr)
        return 1
    if removed:
        print(f"{PROVIDER}: logged out ({path})")
    else:
        print(f"{PROVIDER}: already logged out ({path})")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "login":
        return asyncio.run(_login())
    if args.command == "status":
        return _status()
    if args.command == "logout":
        return _logout()
    raise AssertionError(args.command)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
