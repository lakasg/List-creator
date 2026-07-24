# Putting List Creator on GitHub

Two reasons this is worth the half hour:

1. **History.** Every change is recorded with a date and a reason. If a list
   ever comes out wrong, you can see exactly what changed and go back.
2. **Deployment stops being drag-and-drop.** Updating the server becomes
   `git pull` and a restart, instead of remembering which files you edited
   and copying them across by hand.

Private repositories are free and unlimited on GitHub, so no account change
is needed.

---

## Part 1 — Create the repository

1. Go to <https://github.com/new>
2. **Repository name:** `list-creator`
3. **Description:** `Container loading list to bay list, for the terminal`
4. Select **Private** — this matters, the vessel configurations are
   operational information
5. Leave *Add a README*, *Add .gitignore* and *Choose a licence* all
   **unticked** — you already have those files, and letting GitHub create
   them makes the first push awkward
6. Click **Create repository**

You'll land on a page of setup instructions. Ignore them; the ones below fit
what you already have.

---

## Part 2 — Push from your PC

Put all the project files in one folder — `app.py`, `core.py`, `db.py`,
`seed_data.py`, `legacy_reference.py`, `verify.py`, `verify_configs.py`,
`requirements.txt`, `README.md`, `DEPLOY.md`, `.gitignore`, and the
`templates` folder with its five `.html` files.

`.gitignore` starts with a dot, so Windows Explorer may hide it. Turn on
*View → Hidden items* and check it made it across — without it you will
commit the database and your loading lists.

### If you prefer a window to a terminal

Install **GitHub Desktop** from desktop.github.com. Then:

1. **File → Add local repository**, choose your folder
2. It offers to create a repository — accept
3. Type a summary in the bottom left: `first commit`
4. Click **Commit to main**
5. Click **Publish repository**, tick **Keep this code private**, publish

Done. Skip to Part 3.

### If you prefer the command line

```bash
cd path/to/your/folder

git init -b main
git add .
git status          # check listcreator.db and any .csv are NOT listed
git commit -m "List Creator: web version of the container list generator"

git remote add origin https://github.com/YOUR-USERNAME/list-creator.git
git push -u origin main
```

That `git status` line is the one worth pausing on. You should see the
`.py` files, the templates and the two `.md` files — and nothing else.

When it asks for a password, GitHub wants a **personal access token**, not
your account password:

1. <https://github.com/settings/tokens> → **Generate new token (classic)**
2. Note: `list-creator push`, Expiration: 90 days, tick **repo**
3. Generate, copy it, paste it as the password

Windows will remember it after the first time.

---

## Part 3 — What is deliberately not in the repository

| Not committed | Why |
|---|---|
| `listcreator.db` | Your live vessels. Kept out so deploying an update can never overwrite the ships you have added. |
| `*.csv`, `*.docx` | Loading lists and finished lists — operational, some of it commercially sensitive. |
| `LIST_SECRET` | Lives in the systemd unit on the server. Never in the repository. |
| `venv/`, `__pycache__/` | Rebuilt on each machine. |

The database is not lost by being excluded — the app creates it on first run
and fills it with the original 22 vessels from `seed_data.py`.

---

## Part 4 — Let the server pull from the private repo

The container needs read access. Give it a **deploy key** — a key tied to
this one repository, read-only, so a copy leaking cannot be used to change
anything.

In the Proxmox console for the container:

```bash
apt install -y git
ssh-keygen -t ed25519 -C "listcreator deploy" -f /root/.ssh/id_ed25519 -N ""
cat /root/.ssh/id_ed25519.pub
```

Copy the line it prints. Then on GitHub:

1. Your repository → **Settings** → **Deploy keys** → **Add deploy key**
2. Title: `proxmox listcreator`
3. Key: paste the line
4. Leave **Allow write access** unticked
5. **Add key**

Test it from the container:

```bash
ssh -T git@github.com
```

`Hi YOUR-USERNAME/list-creator! You've successfully authenticated` means it
worked. (It also says shell access is not provided — that's expected.)

> If that hangs or is refused, port 22 outbound is probably blocked. Use
> HTTPS with a read-only fine-grained token instead:
> `git clone https://TOKEN@github.com/YOUR-USERNAME/list-creator.git`

---

## Part 5 — Switch the running server over to git

You already copied the files across with WinSCP. This replaces that folder
with a git clone, keeping your vessel database.

```bash
systemctl stop listcreator

mv /opt/listcreator /opt/listcreator.old
git clone git@github.com:YOUR-USERNAME/list-creator.git /opt/listcreator

# keep the vessels you have already added
cp /opt/listcreator.old/listcreator.db /opt/listcreator/ 2>/dev/null || true

cd /opt/listcreator
python3 -m venv venv
venv/bin/pip install -r requirements.txt
chown -R listcreator:listcreator /opt/listcreator

systemctl start listcreator
systemctl status listcreator
```

Check the site loads and your vessels are still listed, then clear up:

```bash
rm -rf /opt/listcreator.old
```

Take a fresh Proxmox snapshot once you're happy.

---

## Part 6 — How you update it from now on

On your PC, after changing something:

```bash
git add .
git commit -m "say what changed and why"
git push
```

On the server:

```bash
cd /opt/listcreator
git pull
venv/bin/pip install -r requirements.txt    # only if requirements changed
chown -R listcreator:listcreator /opt/listcreator
systemctl restart listcreator
```

If you touched `core.py` or `db.py`, prove nothing drifted before you tell
anyone it's updated:

```bash
venv/bin/python verify_configs.py
venv/bin/python verify.py your_list.csv "CONTSHIP VOW" reference_from_exe.docx
```

Both scripts are in the repository, so they are always on the server
alongside the code they test.

---

## Writing useful commit messages

You are writing to yourself in eight months, when a list came out wrong and
you need to know what changed. `update` and `fix` tell you nothing.

Good:

```
Add MSC LARISSA (bays 1-3, 5-7, 9-11, 13-15, 17, 19-21)
Fix Other grouping missing bay 12 on BG BLUE
```

Say what changed, and if it isn't obvious, why.

---

## Undoing things

| Situation | What to do |
|---|---|
| Broke something, not committed yet | `git checkout -- .` |
| Bad commit, already pushed | `git revert HEAD` then `git push` |
| Want to see what changed and when | `git log --oneline` then `git show <id>` |
| Want the whole server back | Proxmox → Snapshots → Rollback |

`git revert` is safer than `git reset` on anything already pushed: it adds a
new commit undoing the old one, so the history stays honest.

---

## One thing not to commit

If you ever add a login, database password, or API key, it goes in an
environment variable in the systemd unit — not in the code. Once a secret is
committed it stays in the history even after you delete it, and cleaning it
out properly is genuinely awkward.
