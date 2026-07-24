# List Creator — web version

The desktop List Creator, running as a service on your Proxmox server.

The analysis is unchanged. `core.py` is a straight copy of lines 152–537 of
`list-4-3.py` — the document builder and every helper, including all 22 bay
configurations. Nothing in it was retyped or tidied. The web layer only
handles upload, vessel choice, and download.

Verified against your CONTSHIP VOW list: 170 runs, identical text, font
sizes, bold, underline and POD colours.

## Files

| File | What it does |
|---|---|
| `core.py` | The analysis. Unchanged except for where bay ranges are looked up. |
| `db.py` | The vessel database (SQLite) |
| `app.py` | Upload, vessel selection, pre-flight check, download, vessel admin |
| `templates/` | The five pages |
| `seed_data.py` | The original 22 configurations, used once to fill an empty database |
| `legacy_reference.py` | Frozen copy of the old bay-range code, for testing only |
| `verify.py` | Proves the document still matches the desktop version |
| `verify_configs.py` | Proves the database answers the same as the old hard-coded configs |
| `requirements.txt` | Dependencies |

## Vessels

Vessels live in `listcreator.db`, a single SQLite file next to the app. The
first time the app starts it creates that file and fills it with the 22
configurations from the desktop version.

Add, edit and retire vessels at **/vessels** in the browser. Ranges are typed
the way you already know them: `1-3, 5-7, 9, 11-13`. The order matters — the
first range containing a bay is the one used — so they are stored and applied
in the order you type them.

Retiring a vessel hides it from the dropdown without deleting it. Lists
already produced are never affected by any of this.

**Back up** by copying `listcreator.db`. That one file is all your vessel
data.

### Why SQLite

A couple of dozen vessels, one person editing, a handful of reads per list.
SQLite needs no server, no password and no maintenance, and it backs up by
copying a file. Everything vessel-related goes through `db.py`, so moving to
MySQL later means rewriting that one file and nothing else.

## Run it locally first

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open <http://localhost:8000>.

## Deploy on Proxmox

An LXC container is plenty — this is a few seconds of pandas per list.
Debian 12, 2 vCPU, 2 GB RAM, 8 GB disk.

```bash
# in the container
apt update && apt install -y python3 python3-venv python3-pip nginx
adduser --system --group --home /opt/listcreator listcreator

# copy the files to /opt/listcreator, then
cd /opt/listcreator
python3 -m venv venv
venv/bin/pip install -r requirements.txt
chown -R listcreator:listcreator /opt/listcreator
```

`/etc/systemd/system/listcreator.service`:

```ini
[Unit]
Description=List Creator
After=network.target

[Service]
User=listcreator
Group=listcreator
WorkingDirectory=/opt/listcreator
Environment="LIST_SECRET=change-this-to-a-long-random-string"
ExecStart=/opt/listcreator/venv/bin/gunicorn \
    --workers 3 --timeout 120 --bind 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now listcreator
systemctl status listcreator
```

`/etc/nginx/sites-available/listcreator`:

```nginx
server {
    listen 80;
    server_name lists.yourdomain.local;
    client_max_body_size 32M;   # must be at least as large as MAX_CONTENT_LENGTH

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/listcreator /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

Take a Proxmox snapshot once it's working. Rolling back a bad change then
takes seconds.

## Check it after any change

```bash
python verify_configs.py                                    # 36,250 checks
python verify.py loading_list.csv "CONTSHIP VOW" reference_from_exe.docx
```

`verify_configs.py` compares every vessel against a frozen copy of the old
hard-coded code, across every bay from 0 to 120. If you have edited a vessel
on purpose, that vessel will show as different — which is correct, and the
run names it.

Exit code 0 means the output is identical to the desktop version. Generate
the reference with the EXE and **do not open it in Word first** — Word
rewrites the file, and your own edits will show up as differences.

Worth doing this after every Python or pandas upgrade. A library update is
the most likely way the output could quietly drift.

## The pre-flight check

This is the one behaviour the desktop version doesn't have.

Before the download, every container is placed into its bay group using the
same functions the report uses. If any land in `Other` or `Unknown`, the
download is held back and a screen shows how many, which bays, and a strip
of the whole vessel with the stray bays marked.

It exists because picking the wrong vessel doesn't fail — it produces a
clean, professional-looking list with `Other` headings buried in the middle.
On your test data, selecting BG BLUE instead of CONTSHIP VOW put 231 of 460
containers into `Other`, and the document still looked entirely normal.

You can still download anyway. It's a check, not a lock.

## Adding a vessel

Go to **/vessels** and click **Add vessel**. Nothing to edit, nothing to
restart.

Note that this is now the parting of the ways with the desktop EXE: a vessel
added here does not exist there. Once you are working from the web version,
treat it as the only copy and stop using the EXE, otherwise the two will
drift apart without anyone noticing.

## A trap carried over from the desktop version

If you use **Custom** and your ranges begin with `1-3, 5-7`, `1, 3-5` or
`4-6, 8-10`, the app ignores what you typed and uses the built-in
configuration of that name instead. This is what the desktop version has
always done, so the behaviour was left alone — but the web version now tells
you when it happens instead of silently producing a different list.

Adding a vessel avoids it entirely, because vessels are matched by name.

## Known quirks carried over deliberately

These are in the desktop version and were kept, because your output is
correct as it stands and changing them would change the lists you already
work from:

- In `get_position_type`, the generic yard test for `A`, `B`, `C`, `FP`, `R`
  runs before the `E` test, so any yard location containing one of those
  letters returns `Y`. The comment above it says the opposite.
- The same function checks `SSS` against the raw value rather than the
  upper-cased one just above it.
- Rows classified `Other` are dropped from the report; rows with a missing
  `OutStowLoc` are listed separately under Unknown Containers.

If you ever want these looked at, do it as its own change with `verify.py`
runs on several vessels either side — not mixed in with anything else.
