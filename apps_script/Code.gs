// ==========================================================================
// Email Outreach — Google Apps Script
//
// Sends personalized emails directly from your school Gmail account.
// No SendGrid, no "via" tag, no spam warnings.
//
// SETUP:
//   1. Open your Google Sheet
//   2. Go to Extensions → Apps Script
//   3. Delete any code in the editor and paste this entire file
//   4. Update the CONFIG section below to match your sheet
//   5. Click "Run" → select "sendEmails" → authorize when prompted
//   6. To schedule daily: click Triggers (clock icon) → Add Trigger
//      → choose "sendEmails", "Time-driven", "Day timer", pick your time
// ==========================================================================

// ---------------------------------------------------------------------------
// Configuration — update these to match your Google Sheet
// ---------------------------------------------------------------------------
const CONFIG = {
  // Sheet tab name
  sheetName: "Sheet3",

  // Column header names (must match your spreadsheet exactly)
  colFirstName: "First Name",
  colLastName:  "Last Name",
  colEmail:     "Person Email",
  colCompany:   "Company",
  colRole:      "Role",
  colDone:      "Done",

  // Email subject line — supports {first_name}, {last_name}, {company}, {role}
  subject: "Babson Student Interested in {company}",

  // Delay between emails in seconds (to stay under Gmail rate limits)
  delaySeconds: 5,

  // Log sheet name — a new tab will be created if it doesn't exist
  logSheetName: "Email Log",
};

// ---------------------------------------------------------------------------
// Email template — supports {first_name}, {last_name}, {company}, {role}, {a_role}
// Edit this to change your email body.
// ---------------------------------------------------------------------------
const EMAIL_TEMPLATE = `Hi {first_name},

I hope you're doing well. I'm a senior at Babson (Class of 2026) and came across your profile while researching alumni in finance.

I saw that you're currently {a_role} at {company}, and I'd really value the opportunity to learn more about your career path after Babson.

If you're open to it, would you have 15–20 minutes for a quick call in the next few days? I'm happy to work around your schedule.

Best,
Zohair Husain
Babson Class of 2026`;

// ---------------------------------------------------------------------------
// Main functions — run these from the Apps Script editor
// ---------------------------------------------------------------------------

/**
 * Send emails to all contacts that haven't been marked "Done" yet.
 * Run this manually or set up a daily trigger.
 */
function sendEmails() {
  processEmails_(false);
}

/**
 * Preview mode — logs what WOULD be sent without actually sending.
 * Check the execution log (View → Executions) to see the previews.
 */
function dryRun() {
  processEmails_(true);
}

// ---------------------------------------------------------------------------
// Core logic
// ---------------------------------------------------------------------------

function processEmails_(isDryRun) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.sheetName);
  if (!sheet) {
    throw new Error("Sheet tab '" + CONFIG.sheetName + "' not found. Check CONFIG.sheetName.");
  }

  const data = sheet.getDataRange().getValues();
  if (data.length < 2) {
    Logger.log("No data rows found in sheet.");
    return;
  }

  const headers = data[0];
  const colIndex = buildColumnIndex_(headers);
  const logSheet = getOrCreateLogSheet_();

  let sentCount = 0;
  let skippedCount = 0;
  const seenEmails = {};

  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    const rowNumber = i + 1; // 1-indexed sheet row

    const mapped = mapRow_(row, colIndex);

    // Skip rows with no email
    if (!mapped.email) {
      skippedCount++;
      continue;
    }

    // Skip rows already marked done
    const doneVal = String(row[colIndex.done] || "").trim();
    if (doneVal) {
      skippedCount++;
      continue;
    }

    // Deduplicate by email
    const emailLower = mapped.email.toLowerCase();
    if (seenEmails[emailLower]) {
      skippedCount++;
      continue;
    }
    seenEmails[emailLower] = true;

    const subject = renderTemplate_(CONFIG.subject, mapped);
    const body = renderTemplate_(EMAIL_TEMPLATE, mapped);

    if (isDryRun) {
      Logger.log("--- DRY RUN: Email " + (sentCount + 1) + " ---");
      Logger.log("To:      " + mapped.email);
      Logger.log("Subject: " + subject);
      Logger.log("Body:\n" + body);
      Logger.log("---");
      sentCount++;
      continue;
    }

    // Send the email
    try {
      GmailApp.sendEmail(mapped.email, subject, body);

      // Mark the row as done in the sheet
      sheet.getRange(rowNumber, colIndex.done + 1).setValue(
        Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm")
      );

      // Log to the log sheet
      logSheet.appendRow([
        new Date(),
        mapped.email,
        mapped.first_name,
        mapped.last_name,
        mapped.company,
        subject,
        "sent",
      ]);

      Logger.log("Sent to " + mapped.email);
      sentCount++;

      // Delay between emails
      if (i < data.length - 1 && CONFIG.delaySeconds > 0) {
        Utilities.sleep(CONFIG.delaySeconds * 1000);
      }
    } catch (e) {
      Logger.log("FAILED sending to " + mapped.email + ": " + e.message);
      logSheet.appendRow([
        new Date(),
        mapped.email,
        mapped.first_name,
        mapped.last_name,
        mapped.company,
        subject,
        "error: " + e.message,
      ]);
    }
  }

  const mode = isDryRun ? "DRY RUN" : "SEND";
  Logger.log(mode + " complete. " + sentCount + " emails processed, " + skippedCount + " rows skipped.");

  if (!isDryRun && sentCount > 0) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      sentCount + " emails sent, " + skippedCount + " skipped.",
      "Email Outreach Complete",
      10
    );
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildColumnIndex_(headers) {
  const find = function(name) {
    const idx = headers.indexOf(name);
    if (idx === -1) {
      throw new Error("Column '" + name + "' not found in headers: " + headers.join(", "));
    }
    return idx;
  };

  return {
    firstName: find(CONFIG.colFirstName),
    lastName:  find(CONFIG.colLastName),
    email:     find(CONFIG.colEmail),
    company:   find(CONFIG.colCompany),
    role:      find(CONFIG.colRole),
    done:      find(CONFIG.colDone),
  };
}

function mapRow_(row, colIndex) {
  const role = String(row[colIndex.role] || "").trim();
  const roleLower = role.toLowerCase();
  const article = roleLower && "aeiou".indexOf(roleLower[0]) !== -1 ? "an" : "a";
  const aRole = roleLower ? article + " " + roleLower : "";

  return {
    first_name: String(row[colIndex.firstName] || "").trim(),
    last_name:  String(row[colIndex.lastName]  || "").trim(),
    email:      String(row[colIndex.email]     || "").trim(),
    company:    String(row[colIndex.company]   || "").trim(),
    role:       role,
    a_role:     aRole,
  };
}

function renderTemplate_(template, variables) {
  let result = template;
  for (const key in variables) {
    result = result.split("{" + key + "}").join(variables[key]);
  }
  return result;
}

function getOrCreateLogSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let logSheet = ss.getSheetByName(CONFIG.logSheetName);
  if (!logSheet) {
    logSheet = ss.insertSheet(CONFIG.logSheetName);
    logSheet.appendRow(["Timestamp", "To Email", "First Name", "Last Name", "Company", "Subject", "Status"]);
    logSheet.getRange("1:1").setFontWeight("bold");
  }
  return logSheet;
}

// ---------------------------------------------------------------------------
// Custom menu — adds an "Email Outreach" menu to your Google Sheet
// ---------------------------------------------------------------------------

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Email Outreach")
    .addItem("Send Emails", "sendEmails")
    .addItem("Dry Run (Preview Only)", "dryRun")
    .addToUi();
}
