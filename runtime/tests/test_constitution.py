"""Tests for the constitution loader."""

import pytest
import tempfile
import os

from kynd_runtime.control_plane.constitution import Constitution, ConstitutionError


class TestConstitution:
    def test_load_valid_constitution(self):
        yaml_content = """
name: test-agent
mission: A test agent for validation
hard_rules:
  - name: no-delete
    type: block_action_type
    action_types: [delete, destroy]
  - name: require-approval
    type: require_param
    param: approval_id
capabilities:
  - name: send_email
    max_amount: 0
    max_calls_per_day: 100
    allowed_targets:
      - newsletter@kynd.io
  - name: charge_card
    max_amount: 500.00
    max_calls_per_day: 10
money_caps:
  charge_card: 500.00
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            try:
                const = Constitution.load(f.name)
                assert const.name == "test-agent"
                assert const.mission == "A test agent for validation"
                assert len(const.hard_rules) == 2
                assert len(const.capabilities) == 2
            finally:
                os.unlink(f.name)

    def test_load_missing_file(self):
        with pytest.raises(ConstitutionError, match="not found"):
            Constitution.load("/nonexistent/path.yaml")

    def test_load_invalid_yaml(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("not: valid: yaml: [\n")
            f.flush()
            try:
                with pytest.raises(ConstitutionError):
                    Constitution.load(f.name)
            finally:
                os.unlink(f.name)

    def test_load_non_mapping_yaml(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("- item1\n- item2\n")
            f.flush()
            try:
                with pytest.raises(ConstitutionError, match="mapping"):
                    Constitution.load(f.name)
            finally:
                os.unlink(f.name)

    def test_get_capability(self):
        const = Constitution({
            "capabilities": [
                {"name": "send_email", "max_calls_per_day": 100},
                {"name": "charge_card", "max_amount": 500},
            ]
        })
        cap = const.get_capability("send_email")
        assert cap is not None
        assert cap["max_calls_per_day"] == 100

        missing = const.get_capability("nonexistent")
        assert missing is None

    def test_get_money_cap(self):
        const = Constitution({
            "money_caps": {
                "charge_card": 500.00,
                "send_email": 0,
            }
        })
        assert const.get_money_cap("charge_card") == 500.00
        assert const.get_money_cap("nonexistent") is None

    def test_empty_constitution(self):
        const = Constitution({})
        assert const.name == "unnamed"
        assert const.mission == ""
        assert const.hard_rules == []
        assert const.capabilities == []
        assert const.money_caps == {}
