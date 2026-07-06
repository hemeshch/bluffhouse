"""Replay viewer: every run gets a self-contained replay.html — the
ground-truth timeline beside each agent's subjective timeline, no server
required. The template is a static page; the harness injects the run data
into it at write time."""

import json
from importlib import resources

_MARKER = "/*__BLUFFHOUSE_DATA__*/ null"


def render_replay(payload: dict) -> str:
    template = (resources.files("bluffhouse.viewer") / "template.html").read_text()
    if _MARKER not in template:
        raise RuntimeError("viewer template is missing its data marker")
    # "</" would terminate the surrounding <script> tag mid-JSON
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    return template.replace(_MARKER, data, 1)
