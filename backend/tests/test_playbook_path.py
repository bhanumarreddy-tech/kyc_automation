"""Sanity-check playbook YAML path resolution."""

import app.services.playbook_eval as pe
from app.services.playbook_eval import load_playbook


def test_playbook_yaml_loads_under_backend_config() -> None:
    pe._loaded = None
    playbook = load_playbook()
    rules = playbook.get("rules") if isinstance(playbook, dict) else None
    assert isinstance(rules, list)
    assert len(rules) >= 1
