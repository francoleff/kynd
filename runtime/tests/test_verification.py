"""Tests for the verification layer."""

import pytest
from pathlib import Path
import tempfile

from kynd_runtime import Verifier, VerificationError


class TestVerifier:
    def test_all_checks_pass(self):
        v = Verifier()
        v.add_check("positive", lambda p: p["x"] > 0)
        v.add_check("is_string", lambda p: isinstance(p["name"], str))
        result = v.verify({"x": 5, "name": "hello"})
        assert result.passed is True
        assert result.check_results == {"positive": True, "is_string": True}
        assert result.failures == []

    def test_one_check_fails(self):
        v = Verifier()
        v.add_check("positive", lambda p: p["x"] > 0)
        v.add_check("negative", lambda p: p["x"] < 0)
        result = v.verify({"x": 5})
        assert result.passed is False
        assert result.check_results == {"positive": True, "negative": False}
        assert "negative" in result.failures

    def test_multiple_failures(self):
        v = Verifier()
        v.add_check("a", lambda p: False)
        v.add_check("b", lambda p: False)
        result = v.verify({})
        assert result.passed is False
        assert len(result.failures) == 2

    def test_verify_or_raise_passes(self):
        v = Verifier()
        v.add_check("ok", lambda p: True)
        v.verify_or_raise({"ok": True})

    def test_verify_or_raise_fails(self):
        v = Verifier()
        v.add_check("ok", lambda p: False)
        with pytest.raises(VerificationError, match="Verification failed"):
            v.verify_or_raise({"ok": False})

    def test_check_raises_exception(self):
        v = Verifier()
        def bad_check(p):
            raise RuntimeError("boom")
        v.add_check("bad", bad_check)
        result = v.verify({})
        assert result.passed is False
        assert "bad" in result.failures

    def test_file_exists_check(self):
        with tempfile.NamedTemporaryFile() as f:
            v = Verifier()
            v.add_check("file", lambda p: Path(p["path"]).exists())
            result = v.verify({"path": f.name})
            assert result.passed is True

    def test_file_missing(self):
        v = Verifier()
        v.add_check("file", lambda p: Path(p["path"]).exists())
        result = v.verify({"path": "/nonexistent/file.txt"})
        assert result.passed is False

    def test_command_succeeds(self):
        v = Verifier()
        v.add_check("cmd", lambda p: True)  # simulate command check
        result = v.verify({})
        assert result.passed is True

    def test_value_matches(self):
        v = Verifier()
        v.add_check("match", lambda p: p["expected"] == p["actual"])
        result = v.verify({"expected": 42, "actual": 42})
        assert result.passed is True

    def test_value_mismatch(self):
        v = Verifier()
        v.add_check("match", lambda p: p["expected"] == p["actual"])
        result = v.verify({"expected": 42, "actual": 43})
        assert result.passed is False
