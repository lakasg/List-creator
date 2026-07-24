"""
app.py - web front end for List Creator.

The analysis is NOT reimplemented here. Every calculation is delegated to
core.py, which is a verbatim copy of the logic from list-4-3.py. This file
only handles upload, vessel selection, the pre-flight check, and download.
"""
import io
import os
import re
import uuid
import time
import shutil
import logging
import tempfile
import contextlib

import pandas as pd
from flask import (Flask, request, render_template, send_file, redirect,
                   url_for, flash, abort)

import db
from core import ListLogic

app = Flask(__name__)
app.secret_key = os.environ.get("LIST_SECRET", os.urandom(24))
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB upload ceiling

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("listcreator")

db.init_db()   # creates the file and seeds the original 22 on first run


def vessel_names():
    """Names for the dropdown, in database order, with Custom last."""
    return [v["name"] for v in db.list_vessels()] + ["Custom"]


JOB_DIR = os.path.join(tempfile.gettempdir(), "listcreator_jobs")
os.makedirs(JOB_DIR, exist_ok=True)
JOB_TTL = 60 * 30  # keep unclaimed downloads for 30 minutes


def clean_name(raw):
    """
    Make a file name safe without changing how it reads.

    The document heading is this same string, so werkzeug's secure_filename
    is wrong here - it swaps spaces for underscores and "4743 CONTSHIP VOW"
    would be printed at the top of the list as "4743_CONTSHIP_VOW". Strip
    only the characters that are genuinely unsafe in a path.
    """
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '', raw).strip(' .')
    name = re.sub(r'\s+', ' ', name)
    return name[:120] or "List"


def sweep_old_jobs():
    """Delete job folders older than JOB_TTL so temp doesn't grow forever."""
    now = time.time()
    for name in os.listdir(JOB_DIR):
        path = os.path.join(JOB_DIR, name)
        try:
            if now - os.path.getmtime(path) > JOB_TTL:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


def preflight(df, bay_config):
    """
    Work out where every container will land BEFORE the document is built.

    Uses the same two functions the report itself uses, so this cannot drift
    away from the real result. Returns (unplaced_count, bays, total).
    """
    logic = ListLogic()
    d = df.copy()
    d['Bay'] = d['OutStowLoc'].apply(logic.extract_bay_safely)
    d['BayRange'] = d.apply(
        lambda row: (
            'Unknown' if (
                pd.isna(row['OutStowLoc'])
                or str(row['OutStowLoc']).strip() == ''
                or str(row['OutStowLoc']).strip().lower() == 'nan'
            ) else logic.get_custom_bay_range(row['Bay'], row['OutStowLoc'],
                                              bay_config)
        ),
        axis=1
    )
    stray = d['BayRange'].astype(str).str.startswith(('Other', 'Unknown'))
    bays = sorted({int(b) for b in d.loc[stray, 'Bay'] if str(b).isdigit()})
    all_bays = sorted({int(b) for b in d['Bay'] if str(b).isdigit()})
    return int(stray.sum()), bays, all_bays, len(d)


def build(df, bay_config, filename):
    """Run the untouched logic and return the path to the finished document."""
    job = uuid.uuid4().hex
    folder = os.path.join(JOB_DIR, job)
    os.makedirs(folder, exist_ok=True)
    out_path = os.path.join(folder, filename)

    # core.py prints progress to stdout; capture it into the server log
    # rather than editing core.py.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ListLogic().generateWordDoc(df, bay_config, out_path, filename)
    for line in buf.getvalue().splitlines():
        log.info(line)

    return job, out_path


@app.route("/", methods=["GET"])
def index():
    sweep_old_jobs()
    return render_template("index.html", vessels=vessel_names())


@app.route("/generate", methods=["POST"])
def generate():
    upload = request.files.get("csv")
    if not upload or not upload.filename:
        flash("Choose a loading list CSV first.")
        return redirect(url_for("index"))

    vessel = request.form.get("vessel", "").strip()
    from_custom = vessel == "Custom"
    if from_custom:
        vessel = request.form.get("custom", "").strip()
        if not vessel:
            flash("Enter the bay ranges for the custom configuration.")
            return redirect(url_for("index"))

    # A quirk carried over from the desktop version: a typed range list that
    # begins with one of these three prefixes is treated as the built-in
    # configuration of that name, and what you typed is ignored. Behaviour is
    # left alone; the user is told, because otherwise the document quietly
    # isn't what they asked for.
    GENERIC_PREFIXES = ('1-3, 5-7', '1, 3-5', '4-6, 8-10')
    overridden = from_custom and vessel.startswith(GENERIC_PREFIXES)

    name = clean_name(request.form.get("name", "").strip() or "List")
    if not name.lower().endswith(".docx"):
        name += ".docx"

    try:
        df = pd.read_csv(upload.stream, engine="python")
    except Exception as exc:
        log.exception("CSV read failed")
        flash(f"That file could not be read as a CSV: {exc}")
        return redirect(url_for("index"))

    missing = [c for c in ("OutStowLoc", "YardLoc", "ISOCD", "POD", "OutDate")
               if c not in df.columns]
    if missing:
        flash("The CSV is missing these columns: " + ", ".join(missing))
        return redirect(url_for("index"))

    unplaced, bays, all_bays, total = preflight(df, vessel)
    job, path = build(df.copy(), vessel, name)

    if unplaced or overridden:
        if unplaced:
            log.warning("%s containers outside %s (bays %s)",
                        unplaced, vessel, bays)
        return render_template("check.html", vessel=vessel, name=name,
                               unplaced=unplaced, total=total, bays=bays,
                               strip_bays=all_bays, job=job,
                               overridden=overridden)

    return redirect(url_for("download", job=job, filename=name))


@app.route("/download/<job>/<path:filename>")
def download(job, filename):
    if not re.fullmatch(r"[0-9a-f]{32}", job):
        abort(404)
    if filename != clean_name(filename):   # blocks traversal and odd bytes
        abort(404)
    path = os.path.join(JOB_DIR, job, filename)
    if not os.path.isfile(path):
        flash("That list has expired. Generate it again.")
        return redirect(url_for("index"))
    return send_file(path, as_attachment=True, download_name=filename)


@app.route("/vessels")
def vessels():
    return render_template("vessels.html",
                           vessels=db.list_vessels(include_inactive=True),
                           gaps=db.gaps, overlaps=db.overlaps)


@app.route("/vessels/new", methods=["GET", "POST"])
@app.route("/vessels/<int:vessel_id>", methods=["GET", "POST"])
def vessel_form(vessel_id=None):
    vessel = db.get_vessel(vessel_id) if vessel_id else None
    if vessel_id and not vessel:
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "")
        ranges_text = request.form.get("ranges", "")
        notes = request.form.get("notes", "").strip()
        active = request.form.get("active") == "on"
        try:
            if vessel_id:
                db.update_vessel(vessel_id, name, ranges_text, notes, active)
                flash(f"Saved {name}.")
            else:
                db.add_vessel(name, ranges_text, notes, active)
                flash(f"Added {name}.")
            return redirect(url_for("vessels"))
        except ValueError as exc:
            # Hand back what they typed so nothing is retyped.
            return render_template("vessel_form.html", vessel={
                "id": vessel_id, "name": name, "ranges_text": ranges_text,
                "notes": notes, "active": active}, error=str(exc))

    return render_template("vessel_form.html", vessel=vessel, error=None)


@app.route("/vessels/<int:vessel_id>/delete", methods=["POST"])
def vessel_delete(vessel_id):
    vessel = db.get_vessel(vessel_id)
    if not vessel:
        abort(404)
    db.delete_vessel(vessel_id)
    flash(f"Removed {vessel['name']}.")
    return redirect(url_for("vessels"))


@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
