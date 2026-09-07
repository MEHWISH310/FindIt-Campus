"""
Shared building enum -- used by User.assigned_building (which admin works
where) and Report.collection_point (where a found item physically sits).
Kept as short codes (PRP/SJT) that get stored and compared directly, with
human-facing labels kept separately (BUILDING_LABELS) so nothing ever
depends on fuzzy string-matching a free-text location name -- see
custody.py's list_pending_pickups, which filters directly on this enum.

Campus only has two lost & found collection points right now -- add a
member here if a third one opens up. reports.py/custody.py/matches.py
never need to change when that happens; they all just iterate/compare
against this enum.
"""

import enum


class Building(str, enum.Enum):
    PRP = "PRP"
    SJT = "SJT"


BUILDING_LABELS = {
    Building.PRP: "PRP Lost and Found Office",
    Building.SJT: "SJT Lost and Found Office",
}