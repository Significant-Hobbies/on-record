"""People whose statements the index attributes.

The list lives in `people.json` because most of it is mined rather than
written: episode titles across the archives are a ranked list of who the shows
book, and `roster.py` turns that into candidates. Entries marked `curated` were
written by hand and carry titles, employers and aliases; mined entries carry
only a name and how many episodes named them.

Two kinds of alias, deliberately separate:

- `aliases` map whatever the extractor writes back onto a slug. The roster it
  chooses from is one episode's worth of people, so a bare first name is safe.
- `matchAliases` decide whether an episode is credited to someone from its
  title. Those must be distinctive — a common first name here attaches the
  wrong person to an episode, which is how a quote ends up on the wrong page.
  Mined entries get none, so they match on full name only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA = Path(__file__).with_name("people.json")

PEOPLE: list[dict[str, Any]] = json.loads(_DATA.read_text(encoding="utf-8"))
