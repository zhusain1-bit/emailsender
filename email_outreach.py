#!/usr/bin/env python3
"""
Daily Email Outreach Automation

Reads contacts from a Google Sheet, applies an editable email template,
and sends personalized emails via SendGrid with safety confirmations.

Usage:
    python email_outreach.py                # Interactive mode (confirm each email)
    python email_outreach.py --dry-run      # Preview emails without sending
    python email_outreach.py --batch        # Confirm once, then send all
    python email_outreach.py --status-col "Status"  # Track sent status in a sheet column
"""

import argparse
import configparser
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).parent / "config.ini"


def load_config(config_path=CONFIG_PATH):
    """Load and return the parsed config.ini."""
    cfg = configparser.ConfigParser()
    if not config_path.exists():
        print(f"ERROR: Config file not found at {config_path}")
        sys.exit(1)
    cfg.read(config_path)
    return cfg


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]


def get_sheet_data(cfg):
    """Fetch all rows from the configured Google Sheet tab and return a list of dicts."""
    creds_file = Path(__file__).parent / cfg["google_sheets"]["credentials_file"]
    if not creds_file.exists():
        print(f"ERROR: Google credentials file not found at {creds_file}")
        print("See README.md for setup instructions.")
        sys.exit(1)

    creds = Credentials.from_service_account_file(str(creds_file), scopes=SCOPES)
    client = gspread.authorize(creds)

    sheet_id = cfg["google_sheets"]["sheet_id"]
    sheet_name = cfg["google_sheets"]["sheet_name"]

    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)

    # get_all_records returns a list of dicts keyed by header row
    records = worksheet.get_all_records()
    if not records:
        print("No data found in the sheet. Check your sheet_name and sheet_id in config.ini.")
        sys.exit(0)

    return records


def article_for(text):
    """Return 'an' if *text* starts with a vowel sound, otherwise 'a'."""
    if not text:
        return "a"
    return "an" if text[0].lower() in "aeiou" else "a"


def map_record(record, cfg):
    """Map a raw sheet row dict to our standard variable names."""
    role = str(record.get(cfg["google_sheets"]["col_role"], "")).strip()
    role_lower = role.lower()
    a_role = f"{article_for(role_lower)} {role_lower}" if role_lower else ""
    return {
        "first_name": str(record.get(cfg["google_sheets"]["col_first_name"], "")).strip(),
        "last_name": str(record.get(cfg["google_sheets"]["col_last_name"], "")).strip(),
        "email": str(record.get(cfg["google_sheets"]["col_email"], "")).strip(),
        "company": str(record.get(cfg["google_sheets"]["col_company"], "")).strip(),
        "role": role,
        "a_role": a_role,
    }


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

def load_template(cfg):
    """Read the email template file and return its contents as a string."""
    template_path = Path(__file__).parent / cfg["template"]["template_file"]
    if not template_path.exists():
        print(f"ERROR: Template file not found at {template_path}")
        sys.exit(1)
    return template_path.read_text(encoding="utf-8")


def render_template(template_text, variables):
    """Replace {variable} placeholders in the template with actual values."""
    result = template_text
    for key, value in variables.items():
        result = result.replace("{" + key + "}", value)
    return result


def render_subject(cfg, variables):
    """Render the subject line from config with variable substitution."""
    subject_template = cfg["template"]["subject"]
    return render_template(subject_template, variables)


# ---------------------------------------------------------------------------
# Email Sending
# ---------------------------------------------------------------------------

def get_sendgrid_api_key(cfg):
    """Get the SendGrid API key from config or environment variable."""
    api_key = cfg["sendgrid"]["api_key"]
    if api_key == "ENV":
        api_key = os.environ.get("SENDGRID_API_KEY", "")
    if not api_key:
        print("ERROR: No SendGrid API key configured.")
        print("Set 'api_key' in config.ini or the SENDGRID_API_KEY environment variable.")
        sys.exit(1)
    return api_key


def send_email(cfg, to_email, subject, body):
    """Send a single email via SendGrid."""
    sender = cfg["sendgrid"]["sender_email"]
    api_key = get_sendgrid_api_key(cfg)

    message = Mail(
        from_email=sender,
        to_emails=to_email,
        subject=subject,
        plain_text_content=body,
    )

    sg = SendGridAPIClient(api_key)
    response = sg.send(message)

    if response.status_code not in (200, 201, 202):
        raise Exception(f"SendGrid returned status {response.status_code}: {response.body}")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def init_log(cfg):
    """Create the log CSV with headers if it doesn't already exist."""
    log_path = Path(__file__).parent / cfg["logging"]["log_file"]
    if not log_path.exists():
        with open(log_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "to_email", "first_name", "last_name", "company", "subject", "status"])


def log_email(cfg, to_email, first_name, last_name, company, subject, status):
    """Append a row to the email log CSV."""
    log_path = Path(__file__).parent / cfg["logging"]["log_file"]
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            to_email,
            first_name,
            last_name,
            company,
            subject,
            status,
        ])


# ---------------------------------------------------------------------------
# Preview / Confirmation
# ---------------------------------------------------------------------------

def preview_email(index, total, to_email, subject, body):
    """Print a formatted preview of an email to the console."""
    print("\n" + "=" * 70)
    print(f"  EMAIL {index}/{total}")
    print("=" * 70)
    print(f"  To:      {to_email}")
    print(f"  Subject: {subject}")
    print("-" * 70)
    print(body)
    print("=" * 70)


def confirm(prompt="Send this email? [y/n/q] "):
    """Ask for user confirmation. Returns 'y', 'n', or 'q' (quit)."""
    while True:
        choice = input(prompt).strip().lower()
        if choice in ("y", "n", "q"):
            return choice
        print("Please enter y (yes), n (skip), or q (quit).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Daily Email Outreach Automation")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview all emails without actually sending them.",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Show all previews first, then ask for a single confirmation to send all.",
    )
    parser.add_argument(
        "--config",
        default=str(CONFIG_PATH),
        help=f"Path to config file (default: {CONFIG_PATH}).",
    )
    parser.add_argument(
        "--status-col",
        default=None,
        help="Name of a column in the sheet to check; rows where this column is non-empty are skipped.",
    )
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    init_log(cfg)

    # --- Load data and template ---
    print("Fetching contacts from Google Sheets...")
    records = get_sheet_data(cfg)
    template_text = load_template(cfg)

    # --- Build email list ---
    emails_to_send = []
    skipped = 0

    for record in records:
        mapped = map_record(record, cfg)

        # Skip rows with no email address
        if not mapped["email"]:
            skipped += 1
            continue

        # Skip rows already marked as sent (if --status-col is used)
        if args.status_col and str(record.get(args.status_col, "")).strip():
            skipped += 1
            continue

        subject = render_subject(cfg, mapped)
        body = render_template(template_text, mapped)
        emails_to_send.append((mapped, subject, body))

    total = len(emails_to_send)
    print(f"\nFound {total} emails to send ({skipped} rows skipped).")

    if total == 0:
        print("Nothing to do.")
        return

    # --- Dry run mode ---
    if args.dry_run:
        print("\n*** DRY RUN — no emails will be sent ***\n")
        for i, (mapped, subject, body) in enumerate(emails_to_send, 1):
            preview_email(i, total, mapped["email"], subject, body)
        print(f"\nDry run complete. {total} emails previewed.")
        return

    # --- Batch mode ---
    if args.batch:
        for i, (mapped, subject, body) in enumerate(emails_to_send, 1):
            preview_email(i, total, mapped["email"], subject, body)

        print(f"\n{'=' * 70}")
        choice = confirm(f"Send ALL {total} emails above? [y/n/q] ")
        if choice != "y":
            print("Aborted. No emails sent.")
            return

        delay = int(cfg["safety"]["delay_between_emails"])
        sent_count = 0
        for i, (mapped, subject, body) in enumerate(emails_to_send, 1):
            try:
                print(f"Sending {i}/{total} to {mapped['email']}...", end=" ")
                send_email(cfg, mapped["email"], subject, body)
                log_email(cfg, mapped["email"], mapped["first_name"], mapped["last_name"],
                          mapped["company"], subject, "sent")
                print("OK")
                sent_count += 1
            except Exception as e:
                log_email(cfg, mapped["email"], mapped["first_name"], mapped["last_name"],
                          mapped["company"], subject, f"error: {e}")
                print(f"FAILED: {e}")

            if i < total:
                time.sleep(delay)

        print(f"\nDone. {sent_count}/{total} emails sent. See {cfg['logging']['log_file']} for details.")
        return

    # --- Interactive mode (confirm each) ---
    delay = int(cfg["safety"]["delay_between_emails"])
    sent_count = 0

    for i, (mapped, subject, body) in enumerate(emails_to_send, 1):
        preview_email(i, total, mapped["email"], subject, body)
        choice = confirm()

        if choice == "q":
            print(f"\nQuitting. {sent_count} emails sent so far.")
            break
        elif choice == "n":
            log_email(cfg, mapped["email"], mapped["first_name"], mapped["last_name"],
                      mapped["company"], subject, "skipped")
            print("Skipped.")
            continue

        try:
            print(f"Sending to {mapped['email']}...", end=" ")
            send_email(cfg, mapped["email"], subject, body)
            log_email(cfg, mapped["email"], mapped["first_name"], mapped["last_name"],
                      mapped["company"], subject, "sent")
            print("OK")
            sent_count += 1
        except Exception as e:
            log_email(cfg, mapped["email"], mapped["first_name"], mapped["last_name"],
                      mapped["company"], subject, f"error: {e}")
            print(f"FAILED: {e}")

        if i < total:
            time.sleep(delay)

    print(f"\nDone. {sent_count}/{total} emails sent. See {cfg['logging']['log_file']} for details.")


if __name__ == "__main__":
    main()
