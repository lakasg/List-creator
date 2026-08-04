# List Creator

List Creator is a Flask web application for generating Microsoft Word container loading reports from CSV loading-list exports.

The application allows an operator to:

* Upload a loading-list CSV file
* Select a vessel configuration
* Validate container bay assignments
* Identify containers assigned to unknown or uncovered bays
* Generate and download a formatted `.docx` report
* Add, edit, retire, and manage vessel configurations through the browser

The project is designed to run as a lightweight internal web service on Linux.

---

## Features

* Browser-based loading-list processing
* CSV upload and validation
* Vessel-specific bay configuration
* Microsoft Word report generation
* Pre-flight bay assignment check
* Detection of unknown or unmatched container positions
* Vessel configuration management
* SQLite database
* Gunicorn production server support
* Nginx reverse-proxy support
* systemd service configuration
* Verification scripts for report and vessel configuration testing

---

## How it works

A user uploads a loading-list CSV file and selects the appropriate vessel.

List Creator processes the data, assigns each container to a configured vessel bay range, and checks for containers that cannot be matched correctly.

If unmatched containers are detected, the application displays a warning before generating the report. The user can review the affected bays and decide whether to continue.

The final result is generated as a Microsoft Word document.

---

## Technology

* Python
* Flask
* pandas
* python-docx
* SQLite
* Gunicorn
* Jinja2
* Nginx
* systemd

---

## Project structure

```text
List-creator/
├── app.py
├── core.py
├── db.py
├── seed_data.py
├── legacy_reference.py
├── verify.py
├── verify_configs.py
├── requirements.txt
├── deploy.sh
├── update.sh
├── templates/
├── README.md
├── DEPLOY.md
└── GITHUB.md
```

### Main files

| File                  | Purpose                                                                          |
| --------------------- | -------------------------------------------------------------------------------- |
| `app.py`              | Flask application, routes, uploads, downloads, validation, and vessel management |
| `core.py`             | Loading-list processing and Word document generation                             |
| `db.py`               | SQLite database access and vessel configuration management                       |
| `seed_data.py`        | Initial vessel configuration data                                                |
| `templates/`          | HTML templates used by the web interface                                         |
| `verify.py`           | Verifies generated report output                                                 |
| `verify_configs.py`   | Verifies vessel bay configuration behaviour                                      |
| `legacy_reference.py` | Reference implementation used by verification tools                              |
| `requirements.txt`    | Python dependencies                                                              |
| `deploy.sh`           | Deployment helper script                                                         |
| `update.sh`           | Application update helper script                                                 |

---

## Requirements

For local use:

* Python 3.10 or newer
* `python3-venv`
* `python3-pip`

For production deployment:

* Debian or Ubuntu
* Python 3
* Gunicorn
* Nginx
* systemd
* Git

A small server or virtual machine is sufficient for normal internal use.

Suggested minimum resources:

* 2 CPU cores
* 2 GB RAM
* 8 GB storage

---

## Local installation

Clone the repository:

```bash
git clone https://github.com/lakasg/List-creator.git
cd List-creator
```

Create a Python virtual environment:

```bash
python3 -m venv venv
```

Activate it:

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the application:

```bash
python app.py
```

Open:

```text
http://localhost:8000
```

---

## Database

Vessel configurations are stored in a local SQLite database:

```text
listcreator.db
```

If the database does not exist, the application creates it and loads the initial vessel configurations.

The database normally remains outside Git and should not be committed to the repository.

### Backing up the database

Stop or briefly pause application writes before copying the database.

```bash
cp listcreator.db listcreator.db.backup
```

A timestamped backup can be created with:

```bash
cp listcreator.db \
  "listcreator.db.backup-$(date +%Y-%m-%d_%H-%M-%S)"
```

The database contains the vessel definitions managed through the application.

---

## Vessel configuration

Vessels can be managed from:

```text
/vessels
```

The vessel administration interface supports:

* Adding a vessel
* Editing a vessel
* Defining bay ranges
* Retiring a vessel
* Restoring a retired vessel

Example bay configuration:

```text
1-3, 5-7, 9, 11-13
```

Ranges are evaluated in the order they are stored.

Retiring a vessel removes it from normal selection without deleting its database record.

---

## Production deployment

The following example deploys the application to:

```text
/opt/listcreator
```

### 1. Install system packages

```bash
apt update
apt install -y \
  git \
  python3 \
  python3-venv \
  python3-pip \
  nginx
```

---

### 2. Create a service account

Create a system user for the application:

```bash
adduser \
  --system \
  --group \
  --home /opt/listcreator \
  listcreator
```

The service account does not need interactive login access.

---

### 3. Clone the repository

```bash
git clone \
  https://github.com/lakasg/List-creator.git \
  /opt/listcreator
```

Set ownership:

```bash
chown -R listcreator:listcreator /opt/listcreator
```

---

### 4. Create the virtual environment

```bash
cd /opt/listcreator
python3 -m venv venv
```

Install dependencies:

```bash
runuser -u listcreator -- \
  /opt/listcreator/venv/bin/pip install \
  -r /opt/listcreator/requirements.txt
```

Restore ownership:

```bash
chown -R listcreator:listcreator /opt/listcreator
```

---

### 5. Configure the application secret

Generate a secure random value:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Store it in the systemd service configuration as `LIST_SECRET`.

Do not publish production secrets in Git.

---

### 6. Create the systemd service

Create:

```text
/etc/systemd/system/listcreator.service
```

Use:

```ini
[Unit]
Description=List Creator
After=network.target

[Service]
Type=simple
User=listcreator
Group=listcreator
WorkingDirectory=/opt/listcreator
Environment="LIST_SECRET=replace-with-a-long-random-value"
ExecStart=/opt/listcreator/venv/bin/gunicorn \
    --workers 2 \
    --timeout 120 \
    --bind 127.0.0.1:8000 \
    app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Reload systemd:

```bash
systemctl daemon-reload
```

Enable and start the application:

```bash
systemctl enable --now listcreator
```

Check the service:

```bash
systemctl status listcreator --no-pager -l
```

Test Gunicorn locally:

```bash
curl -I http://127.0.0.1:8000
```

Expected response:

```text
HTTP/1.1 200 OK
```

---

## Nginx configuration

Create:

```text
/etc/nginx/sites-available/listcreator
```

Example configuration:

```nginx
server {
    listen 80;
    server_name lists.example.com;

    client_max_body_size 32M;

    location / {
        proxy_pass http://127.0.0.1:8000;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 120;
        proxy_send_timeout 120;
        proxy_read_timeout 120;
    }
}
```

Enable the site:

```bash
ln -s \
  /etc/nginx/sites-available/listcreator \
  /etc/nginx/sites-enabled/listcreator
```

Test the Nginx configuration:

```bash
nginx -t
```

Reload Nginx:

```bash
systemctl reload nginx
```

The application should now be available through the configured hostname.

---

## HTTPS

For a public hostname, configure TLS using a trusted certificate provider such as Let's Encrypt.

On Debian or Ubuntu, Certbot can be installed with:

```bash
apt install -y certbot python3-certbot-nginx
```

Request a certificate:

```bash
certbot --nginx -d lists.example.com
```

Replace `lists.example.com` with the actual hostname.

For internal-only deployments, HTTPS can also be terminated by a reverse proxy, VPN gateway, or access tunnel.

---

## Updating an existing installation

Changes should normally be made on a development machine, committed, and pushed to GitHub before updating production.

Connect to the server:

```bash
ssh root@SERVER_IP
```

Go to the application directory:

```bash
cd /opt/listcreator
```

Check for local changes:

```bash
git status
```

Back up the database:

```bash
cp listcreator.db \
  "listcreator.db.backup-$(date +%Y-%m-%d_%H-%M-%S)"
```

Pull the latest code:

```bash
git pull --rebase origin main
```

Install dependencies if `requirements.txt` changed:

```bash
runuser -u listcreator -- \
  /opt/listcreator/venv/bin/pip install \
  -r /opt/listcreator/requirements.txt
```

Restore ownership:

```bash
chown -R listcreator:listcreator /opt/listcreator
```

Test that the application imports correctly:

```bash
runuser -u listcreator -- \
  /opt/listcreator/venv/bin/python \
  -c "import app; print('App import OK')"
```

Restart the service:

```bash
systemctl restart listcreator
```

Wait for Gunicorn to start:

```bash
sleep 3
```

Check the service:

```bash
systemctl status listcreator --no-pager -l
```

Test the application:

```bash
curl -I http://127.0.0.1:8000
```

Check recent logs:

```bash
journalctl -u listcreator \
  --since "5 minutes ago" \
  --no-pager
```

---

## Verification

The repository includes verification utilities for checking report behaviour and vessel configurations.

### Verify vessel configurations

```bash
source venv/bin/activate
python verify_configs.py
```

This compares stored vessel configurations against the reference implementation.

A configuration intentionally changed through the application may be reported as different from the original reference.

### Verify report output

```bash
source venv/bin/activate
python verify.py \
  loading_list.csv \
  "VESSEL NAME" \
  reference.docx
```

Replace:

* `loading_list.csv` with the source CSV file
* `VESSEL NAME` with the vessel configuration
* `reference.docx` with the expected report

The reference document should be preserved unchanged before verification.

---

## Pre-flight validation

Before generating a report, List Creator validates the bay assignments produced from the uploaded loading list.

The validation screen may report containers assigned to:

* `Other`
* `Unknown`
* Bays outside the selected vessel configuration

This helps detect incorrect vessel selection or incomplete vessel configuration before the final report is generated.

The warning does not permanently block report generation. The user can review the result and continue when appropriate.

---

## Running behind a proxy

Gunicorn listens only on:

```text
127.0.0.1:8000
```

This means it is not directly accessible from other devices.

External access should be provided through:

* Nginx
* Apache
* Caddy
* A VPN
* A private reverse proxy
* A secure access tunnel

Do not expose the Flask development server directly to the internet.

---

## Logs

Check the current service status:

```bash
systemctl status listcreator --no-pager -l
```

Show recent logs:

```bash
journalctl -u listcreator -n 100 --no-pager
```

Show logs from the last five minutes:

```bash
journalctl -u listcreator \
  --since "5 minutes ago" \
  --no-pager
```

Follow logs in real time:

```bash
journalctl -u listcreator -f
```

Press `Ctrl+C` to stop following logs.

---

## Troubleshooting

### Internal Server Error

Check the service logs:

```bash
journalctl -u listcreator -n 100 --no-pager
```

Test the application locally:

```bash
curl -I http://127.0.0.1:8000
```

A running systemd service can still return an HTTP 500 error if the application encounters a Python or template exception.

---

### Gunicorn does not start

Check the service:

```bash
systemctl status listcreator --no-pager -l
```

Check whether port 8000 is listening:

```bash
ss -lntp | grep 8000
```

Test the application import:

```bash
cd /opt/listcreator

runuser -u listcreator -- \
  ./venv/bin/python \
  -c "import app; print('App import OK')"
```

---

### Permission errors

Restore ownership:

```bash
chown -R listcreator:listcreator /opt/listcreator
```

Restart the service:

```bash
systemctl restart listcreator
```

---

### Git reports dubious ownership

When deployment commands are run as root, Git may reject the repository because it is owned by the `listcreator` service account.

Trust the deployment directory:

```bash
git config --global \
  --add safe.directory \
  /opt/listcreator
```

---

### Production contains local changes

Check the changes:

```bash
git status
git diff
```

Do not pull until the changes are understood.

To discard unwanted changes to tracked files:

```bash
git restore .
```

Then pull again:

```bash
git pull --rebase origin main
```

This does not restore deleted ignored files such as the database or virtual environment.

---

### Missing Python module

Install the current dependencies:

```bash
runuser -u listcreator -- \
  /opt/listcreator/venv/bin/pip install \
  -r /opt/listcreator/requirements.txt
```

Restart the service:

```bash
systemctl restart listcreator
```

---

### Template error

Check the logs for Jinja errors:

```bash
journalctl -u listcreator -n 100 --no-pager
```

Inspect template block declarations:

```bash
grep -R -n \
  "block content\|block title" \
  /opt/listcreator/templates
```

A single template must not define the same Jinja block more than once.

---

## Security notes

* Do not commit `listcreator.db`.
* Do not commit production secrets.
* Do not run the application as root.
* Run Gunicorn using the dedicated `listcreator` service account.
* Keep Gunicorn bound to `127.0.0.1`.
* Use Nginx or another reverse proxy for remote access.
* Use HTTPS when the application is accessible outside a trusted network.
* Limit access if uploaded loading lists contain operational or commercially sensitive information.
* Keep Debian, Python, Nginx, and Python dependencies updated.
* Back up the SQLite database regularly.

---

## Backup recommendations

At minimum, back up:

```text
/opt/listcreator/listcreator.db
```

A complete server backup may also include:

```text
/opt/listcreator
/etc/systemd/system/listcreator.service
/etc/nginx/sites-available/listcreator
```

The source code can always be restored from GitHub, but the SQLite database contains local vessel configuration changes and should be backed up separately.

---

## Development workflow

Create a branch:

```bash
git checkout -b feature/example
```

Make and review changes:

```bash
git status
git diff
```

Commit:

```bash
git add .
git commit -m "Describe the change"
```

Push:

```bash
git push -u origin feature/example
```

Merge the change through GitHub, then update production using the deployment steps above.

Avoid editing tracked files directly on the production server.

## Input CSV format

List Creator expects a CSV file containing container loading information.

The column names are case-sensitive and must match the names shown below.

### Required columns

| Column       | Description                                                           | Example       |
| ------------ | --------------------------------------------------------------------- | ------------- |
| `OutStowLoc` | Vessel stowage location. The bay number is extracted from this value. | `280182`      |
| `YardLoc`    | Current yard or operational location of the container.                | `A 138 024 1` |
| `ISOCD`      | Container ISO size and type code.                                     | `45G1`        |
| `POD`        | Port of discharge.                                                    | `LIM`         |
| `OutDate`    | Outbound or loading date. May be empty for some position types.       | `2026-08-04`  |

The application rejects files that do not contain all five required columns.

### Optional columns

| Column             | Description                                                                                |
| ------------------ | ------------------------------------------------------------------------------------------ |
| `Container`        | Container number. Used when identifying containers with a missing `OutStowLoc`.            |
| Additional columns | Other columns may remain in the CSV. They are ignored unless used by the processing logic. |

### Example CSV

```csv
Container,OutStowLoc,YardLoc,ISOCD,POD,OutDate
MSCU1234567,280182,A 138 024 1,45G1,LIM,2026-08-04
TCLU7654321,120184,E1 075 031 1,22G1,PIR,2026-08-04
CMAU1122334,060182,TA1,42G1,BEY,2026-08-04
OOLU9988776,100184,SSS,45P3,ASH,
```

### Column details

#### `OutStowLoc`

`OutStowLoc` represents the vessel stowage position.

The application determines the bay by removing the last four digits.

For example:

```text
280182 → Bay 28
120184 → Bay 12
060182 → Bay 6
```

The value may be stored as text or as a number.

A missing or empty `OutStowLoc` is classified as `Unknown`.

#### `YardLoc`

`YardLoc` is used to determine the position or operational area of the container.

Examples include:

```text
A 138 024 1
B 110 019 1
E1 075 031 1
TA1
TA5
SSS
```

Locations containing common yard identifiers such as `A`, `B`, `C`, `FP`, or `R` are generally grouped as yard containers.

Locations beginning with an E-area format may include structured values such as:

```text
E1 075 031 1
```

Spacing may vary because the parser accepts one or more spaces between these components.

#### `ISOCD`

`ISOCD` is the container ISO code.

The application applies the following groupings:

| ISO code prefix            | Report group          |
| -------------------------- | --------------------- |
| `L`                        | `45 Feet`             |
| `45G`                      | `High Cube`           |
| `42G`                      | `Xamila`              |
| `45P`, `42P`, `22P`, `25P` | `FLAT`                |
| Other values               | The original ISO code |

Examples:

```text
45G1
42G1
22G1
45P3
```

#### `POD`

`POD` is the port-of-discharge code shown in the generated report.

Examples:

```text
LIM
PIR
BEY
ASH
```

The application groups report entries by:

* Vessel bay range
* ISO code group
* Position type
* Port of discharge

#### `OutDate`

`OutDate` is used when determining the container position type.

The application accepts the value as provided by the CSV. Empty values are allowed, although their meaning depends on the associated `YardLoc`.

Use a consistent date format in each file, preferably:

```text
YYYY-MM-DD
```

Example:

```text
2026-08-04
```

### CSV requirements

The uploaded file should meet these requirements:

* The first row must contain column headers.
* Required column names must use the exact spelling and capitalization.
* The file should use comma-separated values.
* Each row should represent one container.
* Empty values should remain empty rather than containing placeholder text.
* The maximum upload size is 32 MB.
* The file should be saved using UTF-8 encoding where possible.

A minimal valid CSV is:

```csv
OutStowLoc,YardLoc,ISOCD,POD,OutDate
280182,A 138 024 1,45G1,LIM,2026-08-04
```

### Common CSV errors

#### Missing required column

The application displays an error such as:

```text
The CSV is missing these columns: OutStowLoc, POD
```

Check that the headers use the exact required names.

#### Incorrect delimiter

A semicolon-separated file may be read as a single column.

Incorrect:

```csv
OutStowLoc;YardLoc;ISOCD;POD;OutDate
```

Correct:

```csv
OutStowLoc,YardLoc,ISOCD,POD,OutDate
```

#### Spreadsheet software changes the values

Spreadsheet applications may:

* Remove leading zeroes
* Convert stowage locations to numbers
* Change date formats
* Export using semicolons instead of commas

Review the exported CSV in a text editor before uploading it.

#### Missing stowage location

Rows with an empty `OutStowLoc` are included in the generated report under the `Unknown Containers` section.

When the optional `Container` column is present, the container number is shown alongside the warning.


---

## License

No license has been specified for this repository.

Without a license, the source code remains protected by default copyright rules and may not automatically be reused, modified, or redistributed by others.

