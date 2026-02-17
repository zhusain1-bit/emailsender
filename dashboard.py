#!/usr/bin/env python3
"""
Email Outreach Dashboard

A simple Flask web app to preview and individually approve outreach emails.
Reads contacts from Google Sheets, skips rows already marked Done, deduplicates
by email address, and lets you approve each email one at a time.

Usage:
    python dashboard.py          # Start on http://localhost:5000
    python dashboard.py --port 8080  # Custom port
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string

from email_outreach import (
    get_worksheet,
    load_config,
    load_template,
    log_email,
    map_record,
    mark_done,
    init_log,
    render_subject,
    render_template,
    send_email,
)

app = Flask(__name__)
CONFIG_PATH = Path(__file__).parent / "config.ini"

# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Email Outreach Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f5f5;
      color: #333;
      padding: 2rem;
    }
    h1 { margin-bottom: 0.25rem; }
    .subtitle { color: #666; margin-bottom: 1.5rem; }
    .stats {
      display: flex; gap: 1.5rem; margin-bottom: 2rem;
    }
    .stat-box {
      background: #fff; border-radius: 8px; padding: 1rem 1.5rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .stat-box .number { font-size: 2rem; font-weight: 700; }
    .stat-box .label { font-size: 0.85rem; color: #888; }
    .card {
      background: #fff; border-radius: 8px; padding: 1.5rem;
      margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      border-left: 4px solid #2563eb;
    }
    .card.sent { border-left-color: #16a34a; opacity: 0.6; }
    .card-header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 0.75rem;
    }
    .card-header h3 { font-size: 1rem; }
    .card-meta { font-size: 0.85rem; color: #666; margin-bottom: 0.5rem; }
    .card-meta span { margin-right: 1.5rem; }
    .subject-line {
      font-weight: 600; margin-bottom: 0.5rem;
      padding: 0.5rem; background: #f9fafb; border-radius: 4px;
    }
    .email-body {
      white-space: pre-wrap; font-size: 0.9rem; line-height: 1.6;
      padding: 1rem; background: #f9fafb; border-radius: 4px;
      margin-bottom: 1rem; max-height: 200px; overflow-y: auto;
    }
    .btn {
      border: none; padding: 0.5rem 1.25rem; border-radius: 6px;
      font-size: 0.9rem; cursor: pointer; font-weight: 500;
      transition: background 0.2s;
    }
    .btn-send { background: #2563eb; color: #fff; }
    .btn-send:hover { background: #1d4ed8; }
    .btn-send:disabled { background: #93c5fd; cursor: not-allowed; }
    .btn-sent { background: #16a34a; color: #fff; cursor: default; }
    .btn-error { background: #dc2626; color: #fff; }
    .refresh-bar {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 1.5rem;
    }
    .btn-refresh {
      background: #fff; border: 1px solid #ddd; padding: 0.5rem 1rem;
      border-radius: 6px; cursor: pointer; font-size: 0.9rem;
    }
    .btn-refresh:hover { background: #f0f0f0; }
    .empty {
      text-align: center; padding: 3rem; color: #888; font-size: 1.1rem;
    }
    .badge {
      display: inline-block; font-size: 0.75rem; padding: 0.2rem 0.5rem;
      border-radius: 4px; font-weight: 600;
    }
    .badge-pending { background: #dbeafe; color: #2563eb; }
    .badge-num { background: #e5e7eb; color: #374151; }
  </style>
</head>
<body>
  <h1>Email Outreach Dashboard</h1>
  <p class="subtitle">Review and approve emails individually before sending</p>

  <div class="stats">
    <div class="stat-box">
      <div class="number" id="pending-count">{{ emails | length }}</div>
      <div class="label">Pending</div>
    </div>
    <div class="stat-box">
      <div class="number">{{ skipped }}</div>
      <div class="label">Skipped / Done</div>
    </div>
    <div class="stat-box">
      <div class="number" id="sent-count">0</div>
      <div class="label">Sent This Session</div>
    </div>
  </div>

  <div class="refresh-bar">
    <span>Showing contacts not yet marked <strong>Done</strong> in the sheet</span>
    <button class="btn-refresh" onclick="location.reload()">Refresh from Sheet</button>
  </div>

  {% if emails %}
  {% for e in emails %}
  <div class="card" id="card-{{ e.row_number }}">
    <div class="card-header">
      <h3>
        <span class="badge badge-num">#{{ loop.index }}</span>
        {{ e.first_name }} {{ e.last_name }}
      </h3>
      <span class="badge badge-pending" id="badge-{{ e.row_number }}">Pending</span>
    </div>
    <div class="card-meta">
      <span>To: <strong>{{ e.email }}</strong></span>
      <span>Company: {{ e.company }}</span>
      <span>Role: {{ e.role }}</span>
    </div>
    <div class="subject-line">Subject: {{ e.subject }}</div>
    <div class="email-body">{{ e.body }}</div>
    <button class="btn btn-send" id="btn-{{ e.row_number }}"
            onclick="sendEmail({{ e.row_number }}, this)">
      Approve &amp; Send
    </button>
  </div>
  {% endfor %}
  {% else %}
  <div class="empty">
    All caught up! No pending emails to send.
  </div>
  {% endif %}

  <script>
    let sentCount = 0;

    async function sendEmail(rowNumber, btn) {
      btn.disabled = true;
      btn.textContent = "Sending...";

      try {
        const resp = await fetch("/send/" + rowNumber, { method: "POST" });
        const data = await resp.json();

        if (data.ok) {
          btn.textContent = "Sent";
          btn.className = "btn btn-sent";
          document.getElementById("card-" + rowNumber).classList.add("sent");
          document.getElementById("badge-" + rowNumber).textContent = "Sent";
          document.getElementById("badge-" + rowNumber).style.background = "#dcfce7";
          document.getElementById("badge-" + rowNumber).style.color = "#16a34a";
          sentCount++;
          document.getElementById("sent-count").textContent = sentCount;
          document.getElementById("pending-count").textContent =
            parseInt(document.getElementById("pending-count").textContent) - 1;
        } else {
          btn.textContent = "Error: " + data.error;
          btn.className = "btn btn-error";
        }
      } catch (err) {
        btn.textContent = "Network Error";
        btn.className = "btn btn-error";
      }
    }
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def build_email_list(cfg):
    """Fetch contacts, filter done/dupes, return (list_of_dicts, skipped_count, worksheet)."""
    worksheet = get_worksheet(cfg)
    records = worksheet.get_all_records()

    col_done = cfg["google_sheets"].get("col_done", "Done")
    template_text = load_template(cfg)
    emails = []
    skipped = 0
    seen = set()

    for idx, record in enumerate(records):
        mapped = map_record(record, cfg)

        if not mapped["email"]:
            skipped += 1
            continue

        if str(record.get(col_done, "")).strip():
            skipped += 1
            continue

        email_lower = mapped["email"].lower()
        if email_lower in seen:
            skipped += 1
            continue
        seen.add(email_lower)

        row_number = idx + 2
        subject = render_subject(cfg, mapped)
        body = render_template(template_text, mapped)

        emails.append({
            "row_number": row_number,
            "first_name": mapped["first_name"],
            "last_name": mapped["last_name"],
            "email": mapped["email"],
            "company": mapped["company"],
            "role": mapped["role"],
            "subject": subject,
            "body": body,
        })

    return emails, skipped, worksheet


@app.route("/")
def index():
    cfg = load_config()
    emails, skipped, _ = build_email_list(cfg)
    return render_template_string(DASHBOARD_HTML, emails=emails, skipped=skipped)


@app.route("/send/<int:row_number>", methods=["POST"])
def send(row_number):
    cfg = load_config()
    init_log(cfg)
    col_done = cfg["google_sheets"].get("col_done", "Done")

    worksheet = get_worksheet(cfg)
    records = worksheet.get_all_records()

    idx = row_number - 2  # header is row 1
    if idx < 0 or idx >= len(records):
        return jsonify(ok=False, error="Invalid row number")

    record = records[idx]

    # Safety: don't re-send if already marked done
    if str(record.get(col_done, "")).strip():
        return jsonify(ok=False, error="Already marked as Done")

    mapped = map_record(record, cfg)
    if not mapped["email"]:
        return jsonify(ok=False, error="No email address for this row")

    template_text = load_template(cfg)
    subject = render_subject(cfg, mapped)
    body = render_template(template_text, mapped)

    # Validate API key before attempting to send (get_sendgrid_api_key calls
    # sys.exit which would kill the Flask process instead of returning JSON)
    api_key = cfg["sendgrid"]["api_key"]
    if api_key == "ENV":
        import os as _os
        api_key = _os.environ.get("SENDGRID_API_KEY", "")
    if not api_key:
        return jsonify(ok=False, error="No SendGrid API key configured. Set SENDGRID_API_KEY env variable.")

    try:
        send_email(cfg, mapped["email"], subject, body)
        mark_done(worksheet, row_number, col_done)
        log_email(cfg, mapped["email"], mapped["first_name"], mapped["last_name"],
                  mapped["company"], subject, "sent")
        return jsonify(ok=True)
    except SystemExit:
        return jsonify(ok=False, error="Configuration error — check SendGrid API key and sender email.")
    except Exception as e:
        log_email(cfg, mapped["email"], mapped["first_name"], mapped["last_name"],
                  mapped["company"], subject, f"error: {e}")
        return jsonify(ok=False, error=str(e))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Email Outreach Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Port to run on (default: 5000)")
    args = parser.parse_args()

    print(f"Starting dashboard on http://localhost:{args.port}")
    app.run(debug=True, port=args.port)
