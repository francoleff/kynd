"""Verification layer — a task is 'done' only when a real check passes.

The model cannot self-certify its own work. Every completed action must
produce a verifiable artifact: a file exists, a test passes, an API returns
200, a value matches. The verifier runs the check and returns pass/fail.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

logger = logging.getLogger(__name__)


class VerificationError(Exception):
    """Raised when verification fails."""


class Verifier:
    """Run verification checks against task output.
    
    Usage:
        verifier = Verifier()
        verifier.add_check("file_exists", lambda p: Path(p["path"]).exists())
        result = verifier.verify({"path": "/tmp/output.txt"})
    """

    def __init__(self, allow_empty: bool = False) -> None:
        self._checks: dict[str, Callable[[dict[str, Any]], bool]] = {}
        self._allow_empty = allow_empty

    def add_check(self, name: str, check: Callable[[dict[str, Any]], bool]) -> None:
        """Register a verification check."""
        if not callable(check):
            raise TypeError(f"check for '{name}' must be callable")
        if name in self._checks:
            logger.warning("Overriding existing verification check '%s'", name)
        self._checks[name] = check

    def __len__(self) -> int:
        return len(self._checks)

    def verify(self, params: dict[str, Any]) -> VerificationResult:
        """Run all registered checks against params.

        Returns a VerificationResult with pass/fail and details for each check.

        A verifier with no checks FAILS. "Nothing was checked" is not evidence
        that the work was done — that is the exact false-confidence this layer
        exists to prevent. Pass ``allow_empty=True`` to opt out deliberately.
        """
        results: dict[str, bool] = {}
        failures: list[str] = []
        errors: dict[str, str] = {}

        if not self._checks and not self._allow_empty:
            return VerificationResult(
                passed=False,
                check_results={},
                failures=["<no checks registered>"],
                errors={
                    "<no checks registered>": (
                        "Verifier has no checks; nothing was verified. Register at "
                        "least one check, or construct with allow_empty=True."
                    )
                },
            )

        for name, check in self._checks.items():
            try:
                passed = bool(check(params))
            except Exception as e:
                passed = False
                errors[name] = f"{type(e).__name__}: {e}"
                logger.warning("Check '%s' raised exception: %s", name, e)
            results[name] = passed
            if not passed:
                failures.append(name)

        all_passed = len(failures) == 0
        return VerificationResult(
            passed=all_passed,
            check_results=results,
            failures=failures,
            errors=errors,
        )

    def verify_or_raise(self, params: dict[str, Any]) -> None:
        """Verify and raise VerificationError if any check fails."""
        result = self.verify(params)
        if not result.passed:
            detail = ", ".join(
                f"{name} ({result.errors[name]})" if name in result.errors else name
                for name in result.failures
            )
            raise VerificationError(f"Verification failed: {detail}")


@dataclass
class VerificationResult:
    """Result of a verification run."""

    passed: bool
    check_results: dict[str, bool]
    failures: list[str]
    errors: dict[str, str] = field(default_factory=dict)


def run_command(
    cmd: str | Sequence[str],
    timeout: int = 30,
    shell: bool = False,
    cwd: str | None = None,
) -> bool:
    """Run a command and return True if it exits 0.

    Prefer passing a list of arguments — ``["pytest", "-q"]`` — which executes
    directly with no shell involved. A string with ``shell=True`` runs through
    the shell and will happily execute ``rm -rf /`` if that is what it is given;
    only do that with a command you control. Never build such a string from
    model output or webhook input.
    """
    if isinstance(cmd, str) and not shell:
        cmd = shlex.split(cmd)
    try:
        result = subprocess.run(  # noqa: S603 -- args are shlex-split or explicit
                                   # shell=True opt-in; see docstring above
            cmd,
            shell=shell,  # nosec B602
            # shell=True is opt-in only (default False); the caller must
            # explicitly request it and is responsible for never passing
            # untrusted input when they do — documented in this function's
            # docstring above.
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.warning("Command timed out after %ss: %s", timeout, cmd)
        return False
    except (OSError, ValueError) as e:
        logger.warning("Command could not be run (%s): %s", type(e).__name__, cmd)
        return False


def file_exists(path: str) -> bool:
    """Check if a file exists."""
    return os.path.exists(path)


def command_succeeds(cmd: str | Sequence[str], timeout: int = 30) -> bool:
    """Check if a command exits 0. Argument list preferred; no shell by default."""
    return run_command(cmd, timeout=timeout)


def value_matches(expected: Any, actual: Any) -> bool:
    """Check if two values match."""
    return bool(expected == actual)
