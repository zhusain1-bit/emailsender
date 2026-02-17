# Email Outreach Automation

Reads contacts from a Google Sheet and sends personalized emails via SendGrid with preview, confirmation, dry-run, and logging.

## Files

| File | Purpose |
|---|---|
| `email_outreach.py` | Main script |
| `config.ini` | All settings (Sheet ID, SMTP, columns, schedule) |
| `template.txt` | Editable email body template |
| `requirements.txt` | Python dependencies |
| `email_log.csv` | Auto-generated log of sent emails |
| `credentials.json` | Google API credentials (you create this — **never commit it**) |

## Setup

### 1. Python environment

```bash
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 2. Google Sheets API credentials

You need a **service account** so the script can read your Google Sheet.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable the **Google Sheets API**:
   - Navigate to **APIs & Services → Library**
   - Search for "Google Sheets API" and click **Enable**
4. Create a service account:
   - Go to **APIs & Services → Credentials**
   - Click **Create Credentials → Service Account**
   - Give it a name (e.g., `email-outreach-reader`)
   - Click **Done**
5. Create a key for the service account:
   - Click on the service account you just created
   - Go to the **Keys** tab
   - Click **Add Key → Create new key → JSON**
   - Save the downloaded file as `credentials.json` in this project folder
6. Share your Google Sheet with the service account:
   - Open the JSON file and find the `client_email` field (looks like `name@project.iam.gserviceaccount.com`)
   - Open your Google Sheet in a browser
   - Click **Share** and add that email address with **Viewer** access

### 3. SendGrid API key

SendGrid lets you send emails via API — no app password or university SMTP access needed.

1. Sign up for a free account at [https://signup.sendgrid.com/](https://signup.sendgrid.com/) (100 emails/day free)
2. Go to **Settings → API Keys** ([https://app.sendgrid.com/settings/api_keys](https://app.sendgrid.com/settings/api_keys))
3. Click **Create API Key**, give it a name (e.g., "email-outreach"), select **Restricted Access** with **Mail Send** permission, and click **Create & View**
4. Copy the API key (you won't be able to see it again)

Set the API key as an environment variable (recommended):

```bash
export SENDGRID_API_KEY="SG.your-api-key-here"
```

Or put it directly in `config.ini` under `api_key` (less secure — avoid committing).

5. **Verify your sender email**: Go to **Settings → Sender Authentication** ([https://app.sendgrid.com/settings/sender_auth](https://app.sendgrid.com/settings/sender_auth)) and verify the email address you want to send from (e.g., your Babson email). SendGrid will send a verification link to that address.

### 4. Edit config.ini

Update these values in `config.ini`:

- `sender_email` — your Babson email address
- `sheet_id` — already set to your sheet
- Column names — already set to match your sheet (`First Name`, `Last Name`, `Person Email`, `Company Website`, `Role`)
- `subject` — the email subject line (supports `{first_name}`, `{company}`, `{role}` variables)
- `run_time` / `timezone` — for scheduling

### 5. Edit template.txt

Open `template.txt` and customize the email body. Available variables:

| Variable | Replaced with |
|---|---|
| `{first_name}` | First Name column |
| `{last_name}` | Last Name column |
| `{email}` | Person Email column |
| `{company}` | Company Website column |
| `{role}` | Role column |

## Usage

### Interactive mode (confirm each email)

```bash
python email_outreach.py
```

You'll see a preview of each email and be asked `[y/n/q]` before sending.

### Dry run (preview only, no sending)

```bash
python email_outreach.py --dry-run
```

### Batch mode (confirm once for all)

```bash
python email_outreach.py --batch
```

Shows all email previews, then asks once whether to send them all.

### Skip already-contacted rows

If you have a column in your sheet that tracks status (e.g., "Status"), you can skip rows where that column is non-empty:

```bash
python email_outreach.py --status-col "Status"
```

## Scheduling (daily run)

### macOS / Linux (cron)

```bash
crontab -e
```

Add a line like this (runs daily at 9:00 AM):

```
0 9 * * * cd /path/to/emailsender && /path/to/venv/bin/python email_outreach.py --batch >> cron_output.log 2>&1
```

> **Important:** For unattended (cron) use, use `--batch` mode. Interactive mode requires a terminal.

### Windows (Task Scheduler)

1. Open **Task Scheduler**
2. Click **Create Basic Task**
3. Set trigger to **Daily** at your desired time
4. Set action to **Start a Program**:
   - Program: `C:\path\to\venv\Scripts\python.exe`
   - Arguments: `email_outreach.py --batch`
   - Start in: `C:\path\to\emailsender`

## Logging

Every email attempt is logged to `email_log.csv` with:

- Timestamp
- Recipient email
- First name, last name, company
- Subject line
- Status (`sent`, `skipped`, or `error: <message>`)

## Troubleshooting

| Problem | Solution |
|---|---|
| `credentials.json not found` | Complete the Google Sheets API setup in step 2 |
| `No data found in the sheet` | Check that `sheet_name` in config.ini matches your tab name exactly ("Email") |
| `SendGrid returned status 403` | Verify your sender email is authenticated in SendGrid Sender Authentication |
| `No SendGrid API key configured` | Set the SENDGRID_API_KEY environment variable or update config.ini |
| `Permission denied` on Google Sheet | Share the sheet with the service account email from credentials.json |
| Rate limiting / throttling | Increase `delay_between_emails` in config.ini |
