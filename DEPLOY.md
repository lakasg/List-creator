# Deploying List Creator on Proxmox — step by step

This assumes you have never done this before. Follow it in order. Each stage
ends with something you can check, so you always know whether it worked
before moving on.

Total time: about 30 minutes.

**What you are building:** a small Linux container on your Proxmox server that
runs the app all the time, so anyone on the terminal network can open it in a
browser. No EXE to copy around, no Python on anyone's PC.

---

## Stage 1 — Create the container

A **container** (LXC) is a lightweight Linux machine. It boots in a second and
uses very little memory. That's all this app needs.

### 1.1 Get a Debian template

In the Proxmox web interface:

1. In the left tree, click your server name (e.g. `pve`)
2. Click **local (pve)** underneath it
3. Click **CT Templates** in the middle menu
4. Click the **Templates** button at the top
5. Find `debian-12-standard` in the list, select it, click **Download**

Wait for it to finish. You'll see a log window; close it when it says `TASK OK`.

### 1.2 Create the container

1. Click the blue **Create CT** button, top right
2. Fill in each tab:

**General**
- Hostname: `listcreator`
- Password: pick one and **write it down** — you'll need it in a minute
- Leave *Unprivileged container* ticked

**Template**
- Storage: `local`
- Template: `debian-12-standard`

**Disks**
- Disk size: `8` GB

**CPU**
- Cores: `2`

**Memory**
- Memory: `2048` MB
- Swap: `512` MB

**Network**
- Bridge: `vmbr0`
- IPv4: select **DHCP**

**DNS** — leave everything blank (it inherits from the host)

3. Click **Next**, then **Finish**

### 1.3 Start it and find its address

1. In the left tree, click your new `listcreator` container
2. Click **Start** (top right)
3. Click **Console** in the middle menu
4. Log in: username `root`, and the password you wrote down
5. Type this and press Enter:

```bash
hostname -I
```

You'll see something like `192.168.1.47`. **Write this down** — this is your
app's address. Everywhere below that says `CONTAINER_IP`, use this number.

> If the address later changes, see *Giving it a fixed address* at the end.

---

## Stage 2 — Install what the app needs

Still in the Console, run these one at a time:

```bash
apt update && apt upgrade -y
```

```bash
apt install -y python3 python3-venv python3-pip nginx openssh-server
```

That last one takes a couple of minutes.

### Turn on file transfer

You need to copy files in from your PC, so allow login over the network:

```bash
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
systemctl restart ssh
```

**Check it worked:**

```bash
systemctl is-active ssh
```

Should print `active`.

---

## Stage 3 — Copy the files across

### On Windows

1. Download **WinSCP** (free) from winscp.net and install it
2. Open it. In the login box:
   - File protocol: **SFTP**
   - Host name: your `CONTAINER_IP`
   - User name: `root`
   - Password: the one you wrote down
3. Click **Login**. Say yes to the security warning the first time.

You now have your PC on the left, the container on the right.

4. On the right side, navigate to `/opt`
5. Create a folder there called `listcreator` (right-click → New → Directory)
6. Go into it
7. Drag these across from the left:

```
app.py
core.py
db.py
seed_data.py
legacy_reference.py
verify.py
verify_configs.py
requirements.txt
README.md
templates/          <- the whole folder, with the 5 html files inside
```

**Check it worked** — back in the Proxmox Console:

```bash
ls /opt/listcreator /opt/listcreator/templates
```

You should see all the files, and five `.html` files inside `templates`.

### On Mac or Linux

From the folder holding the files:

```bash
scp -r *.py requirements.txt README.md templates root@CONTAINER_IP:/opt/listcreator/
```

(Create the folder first: `ssh root@CONTAINER_IP "mkdir -p /opt/listcreator"`)

---

## Stage 4 — Install the Python libraries and test it

Back in the Proxmox Console:

```bash
cd /opt/listcreator
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

This takes 2–3 minutes — pandas is a big download. You'll see a lot of
scrolling text. It's finished when you get your prompt back.

> If it fails with a compiler error, run
> `apt install -y build-essential python3-dev` and try the pip line again.

Now start it by hand, just to see it work:

```bash
venv/bin/python app.py
```

You should see:

```
 * Running on http://0.0.0.0:8000
```

**Now open a browser on your PC and go to:**

```
http://CONTAINER_IP:8000
```

You should see the List Creator page. Upload a loading list, pick a vessel,
and check the document comes out right.

The vessel database is created automatically the first time the app starts,
already filled with the 22 configurations from the desktop version. Click
**Vessels** in the top right to see them, and to add new ships.

When you're happy, go back to the Console and press **Ctrl+C** to stop it.

> If the page doesn't load, check you typed the right IP and included
> `:8000`. If it still doesn't, run `hostname -I` again — the address may
> have changed.

---

## Stage 5 — Make it run permanently

Right now the app only runs while you're watching it. This stage makes it
start on its own, and restart if it ever crashes or the server reboots.

### 5.1 Create a user for it

Running a web app as `root` is unnecessary risk. Give it its own account:

```bash
adduser --system --group --home /opt/listcreator listcreator
chown -R listcreator:listcreator /opt/listcreator
```

### 5.2 Make a password for the app

```bash
openssl rand -hex 32
```

Copy the long string it prints. You'll paste it in the next step.

### 5.3 Create the service

```bash
nano /etc/systemd/system/listcreator.service
```

Paste this in (right-click pastes in the Proxmox console), replacing
`PASTE_THE_RANDOM_STRING_HERE` with what you just copied:

```ini
[Unit]
Description=List Creator
After=network.target

[Service]
User=listcreator
Group=listcreator
WorkingDirectory=/opt/listcreator
Environment="LIST_SECRET=PASTE_THE_RANDOM_STRING_HERE"
ExecStart=/opt/listcreator/venv/bin/gunicorn --workers 3 --timeout 120 --bind 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Save and exit: **Ctrl+O**, **Enter**, **Ctrl+X**.

### 5.4 Turn it on

```bash
systemctl daemon-reload
systemctl enable --now listcreator
systemctl status listcreator
```

**Check it worked:** you want to see `active (running)` in green.
Press **q** to get your prompt back.

> If it says `failed`, run `journalctl -u listcreator -n 40` to see why.
> Nine times out of ten it's a typo in the service file.

---

## Stage 6 — Drop the port number

Right now people would have to type `:8000`. This stage lets them just use
the address.

```bash
nano /etc/nginx/sites-available/listcreator
```

Paste this in:

```nginx
server {
    listen 80 default_server;
    server_name _;
    client_max_body_size 32M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Save and exit (**Ctrl+O**, **Enter**, **Ctrl+X**), then:

```bash
rm -f /etc/nginx/sites-enabled/default
ln -s /etc/nginx/sites-available/listcreator /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

`nginx -t` should say `syntax is ok` and `test is successful`. If it doesn't,
fix the file before reloading.

**Check it worked:** open `http://CONTAINER_IP` in your browser — no port
number this time.

---

## Stage 7 — Snapshot it

Now that it works, take a snapshot so you can undo any future mistake in
seconds.

1. In Proxmox, click your `listcreator` container
2. Click **Snapshots**
3. Click **Take Snapshot**
4. Name: `working`, Description: `first working install`
5. Click **Take Snapshot**

If you ever break something, come back here, select `working`, and click
**Rollback**.

---

## You're done

The app is at `http://CONTAINER_IP` and will stay running through reboots.

---

## Giving it a fixed address

DHCP means the address could change one day, which would break everyone's
bookmarks. Once things are stable, pin it:

1. Stop the container in Proxmox
2. Click the container → **Network** → double-click `eth0`
3. Change IPv4 from DHCP to **Static**
4. IPv4/CIDR: the address you've been using plus `/24`, e.g. `192.168.1.47/24`
5. Gateway: your router's address, usually `192.168.1.1`
6. OK, then Start the container

Better still, ask whoever runs your network to reserve that address for this
container in the DHCP server.

---

## Backing up your vessels

The vessels live in one file: `/opt/listcreator/listcreator.db`. Copy it and
you have copied everything.

A nightly copy, kept for a week:

```bash
mkdir -p /opt/listcreator/backups
crontab -e
```

Add this line, save and exit:

```
0 2 * * * sqlite3 /opt/listcreator/listcreator.db ".backup /opt/listcreator/backups/vessels-$(date +\%u).db"
```

You'll need `apt install -y sqlite3` for that. Proxmox snapshots cover you as
well, but this gives you the vessel data on its own, which is quicker to
restore from.

## Everyday commands

Run these in the Proxmox Console for the container.

| What you want | Command |
|---|---|
| Is it running? | `systemctl status listcreator` |
| Restart it | `systemctl restart listcreator` |
| See what it's doing | `journalctl -u listcreator -f` (Ctrl+C to stop) |
| See recent errors | `journalctl -u listcreator -n 50` |

## Updating the app later

After changing any file (via WinSCP):

```bash
chown -R listcreator:listcreator /opt/listcreator
systemctl restart listcreator
```

If you changed `core.py` or `db.py`, check nothing has drifted:

```bash
cd /opt/listcreator
venv/bin/python verify_configs.py
venv/bin/python verify.py your_list.csv "CONTSHIP VOW" reference_from_exe.docx
```

The first compares every vessel against the old hard-coded code. If you have
edited a vessel on purpose, expect that one to show as different.

Anything other than `IDENTICAL` means stop and look at what changed.

---

## A note on security

This setup has no login page and no HTTPS. That is fine on a private terminal
network where everyone is trusted, and it keeps things simple.

Do **not** forward it through your firewall to the internet as it stands.
If you ever need access from outside, that needs a login and HTTPS first —
worth doing properly rather than bolting on.

One tidy-up worth doing once you're finished copying files: turn root SSH
login back off.

```bash
sed -i 's/^PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart ssh
```

You can still get in through the Proxmox Console any time.
