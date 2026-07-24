"""
db.py - where the bay configurations live.

SQLite, one file on disk. This is the right size of database for the job:
a couple of dozen vessels, one person editing at a time, a handful of reads
per list. It needs no server, no password, and no maintenance, and it backs
up by copying one file.

Everything the rest of the app does with vessels goes through this module,
so moving to MySQL or Postgres later means rewriting this file only.
"""
import os
import re
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.environ.get(
    "LIST_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "listcreator.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS vessel (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    active      INTEGER NOT NULL DEFAULT 1,
    notes       TEXT    NOT NULL DEFAULT '',
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS bay_range (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    vessel_id  INTEGER NOT NULL REFERENCES vessel(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL,
    bay_start  INTEGER NOT NULL,
    bay_end    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_range_vessel ON bay_range(vessel_id, position);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(seed=True):
    """Create the tables, and fill them the first time from seed_data.py."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        if seed and not conn.execute("SELECT 1 FROM vessel LIMIT 1").fetchone():
            from seed_data import ORIGINAL_CONFIGS
            for name, ranges in ORIGINAL_CONFIGS.items():
                _insert(conn, name, ranges, notes="from the desktop version")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _insert(conn, name, ranges, active=1, notes=""):
    cur = conn.execute(
        "INSERT INTO vessel (name, active, notes, updated_at) VALUES (?,?,?,?)",
        (name.strip(), 1 if active else 0, notes, _now()))
    vid = cur.lastrowid
    conn.executemany(
        "INSERT INTO bay_range (vessel_id, position, bay_start, bay_end) "
        "VALUES (?,?,?,?)",
        [(vid, i, a, b) for i, (a, b) in enumerate(ranges)])
    return vid


# ---------------------------------------------------------------- ranges

def parse_ranges(text):
    """
    Turn "1-3, 5-7, 9" into [(1, 3), (5, 7), (9, 9)].

    Order is kept exactly as typed, because the first range that contains a
    bay is the one that wins. Reordering the text changes the result.
    """
    ranges = []
    for i, part in enumerate([p.strip() for p in str(text).split(",")], start=1):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
        elif re.fullmatch(r"\d+", part):
            a = b = int(part)
        else:
            raise ValueError(
                f'Entry {i} ("{part}") is not a bay or a bay range. '
                'Use numbers like 9 or ranges like 5-7, separated by commas.')
        if a > b:
            raise ValueError(f'Entry {i} ("{part}") counts backwards. '
                             f'Write it as {b}-{a}.')
        ranges.append((a, b))
    if not ranges:
        raise ValueError("Enter at least one bay range, for example 1-3, 5-7.")
    return ranges


def format_ranges(ranges):
    return ", ".join(f"{a}-{b}" if a != b else str(a) for a, b in ranges)


def overlaps(ranges):
    """Bays covered by more than one range. The earlier range always wins."""
    seen, clash = set(), set()
    for a, b in ranges:
        for bay in range(a, b + 1):
            (clash if bay in seen else seen).add(bay)
    return sorted(clash)


def gaps(ranges):
    """Bays inside the vessel's span that no range covers - these go to Other."""
    if not ranges:
        return []
    covered = {bay for a, b in ranges for bay in range(a, b + 1)}
    lo, hi = min(covered), max(covered)
    return [b for b in range(lo, hi + 1) if b not in covered]


# ---------------------------------------------------------------- reads

def get_ranges(name):
    """
    The ranges for one vessel, in order, or None if there is no such vessel.

    Returning None matters: core.py falls back to its original text parsing
    when it gets None, which is how "Custom" and the generic configurations
    keep working.
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM vessel WHERE name = ? AND active = 1",
            (str(name).strip(),)).fetchone()
        if not row:
            return None
        rows = conn.execute(
            "SELECT bay_start, bay_end FROM bay_range WHERE vessel_id = ? "
            "ORDER BY position", (row["id"],)).fetchall()
    return [(r["bay_start"], r["bay_end"]) for r in rows] or None


def list_vessels(include_inactive=False):
    where = "" if include_inactive else "WHERE active = 1"
    with connect() as conn:
        vessels = conn.execute(
            f"SELECT * FROM vessel {where} ORDER BY id").fetchall()
        out = []
        for v in vessels:
            rows = conn.execute(
                "SELECT bay_start, bay_end FROM bay_range WHERE vessel_id = ? "
                "ORDER BY position", (v["id"],)).fetchall()
            ranges = [(r["bay_start"], r["bay_end"]) for r in rows]
            out.append({"id": v["id"], "name": v["name"],
                        "active": bool(v["active"]), "notes": v["notes"],
                        "updated_at": v["updated_at"], "ranges": ranges,
                        "ranges_text": format_ranges(ranges)})
    return out


def get_vessel(vessel_id):
    for v in list_vessels(include_inactive=True):
        if v["id"] == vessel_id:
            return v
    return None


# ---------------------------------------------------------------- writes

def add_vessel(name, ranges_text, notes="", active=True):
    ranges = parse_ranges(ranges_text)
    name = name.strip()
    if not name:
        raise ValueError("Give the vessel a name.")
    with connect() as conn:
        if conn.execute("SELECT 1 FROM vessel WHERE name = ?",
                        (name,)).fetchone():
            raise ValueError(f'There is already a vessel called "{name}".')
        return _insert(conn, name, ranges, active, notes)


def update_vessel(vessel_id, name, ranges_text, notes="", active=True):
    ranges = parse_ranges(ranges_text)
    name = name.strip()
    if not name:
        raise ValueError("Give the vessel a name.")
    with connect() as conn:
        clash = conn.execute(
            "SELECT 1 FROM vessel WHERE name = ? AND id <> ?",
            (name, vessel_id)).fetchone()
        if clash:
            raise ValueError(f'There is already a vessel called "{name}".')
        conn.execute(
            "UPDATE vessel SET name=?, active=?, notes=?, updated_at=? "
            "WHERE id=?",
            (name, 1 if active else 0, notes, _now(), vessel_id))
        conn.execute("DELETE FROM bay_range WHERE vessel_id = ?", (vessel_id,))
        conn.executemany(
            "INSERT INTO bay_range (vessel_id, position, bay_start, bay_end) "
            "VALUES (?,?,?,?)",
            [(vessel_id, i, a, b) for i, (a, b) in enumerate(ranges)])


def delete_vessel(vessel_id):
    with connect() as conn:
        conn.execute("DELETE FROM vessel WHERE id = ?", (vessel_id,))


if __name__ == "__main__":
    init_db()
    print(f"database ready at {DB_PATH}")
    for v in list_vessels():
        print(f"  {v['name']:<22} {v['ranges_text']}")
