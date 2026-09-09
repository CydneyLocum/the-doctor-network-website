# The Doctor Network V5 — Go-Live Setup

V5 is wired for:
- all website form submissions to email **cydney@thedoctornetwork.com.au**
- jobs to come from one Google Sheet in The Doctor Network Google Drive
- the same Google Sheet to later act as the CRM's job source of truth

## 1. Create the Jobs Google Sheet
Create a Google Sheet in The Doctor Network Drive, ideally named:

**The Doctor Network - Jobs**

Import `jobs-template.csv` into a tab named exactly:

**Jobs**

The public website only publishes rows where:
- `Status` = `Live`
- `Publish to Website` = `Yes`

Keep `Public Organisation Name?` as `No` for confidential listings.

## 2. Add the Google Apps Script
From the Jobs spreadsheet:
1. Open **Extensions → Apps Script**.
2. Replace the default code with `google-apps-script/Code.gs`.
3. Copy the Google Sheet ID from the spreadsheet URL:
   `https://docs.google.com/spreadsheets/d/THIS_IS_THE_SHEET_ID/edit`
4. Replace `PASTE_YOUR_GOOGLE_SHEET_ID_HERE` in `Code.gs`.
5. Save.

## 3. Deploy as a Web App
In Apps Script:
1. Click **Deploy → New deployment**.
2. Select **Web app**.
3. Execute as: **Me**.
4. Who has access: **Anyone**.
5. Deploy and authorise.
6. Copy the deployment URL ending in `/exec`.

## 4. Connect the website
Open:

`assets/config.js`

Replace:

`PASTE_YOUR_GOOGLE_APPS_SCRIPT_WEB_APP_URL_HERE`

with your `/exec` URL.

That single endpoint powers:
- Join the Network submissions
- Find a Doctor submissions
- Contact submissions
- Job enquiry submissions
- Live website opportunities
- Individual opportunity pages

## 5. Publish to GitHub
Upload the contents of the website folder to your GitHub repository and enable GitHub Pages, or connect the repository to your preferred static hosting provider.

## Form routing
Current destination:
**cydney@thedoctornetwork.com.au**

Future development task already planned:
change submission routing to **hello@thedoctornetwork.com.au** when the business grows.

## CV uploads
Doctor CVs are emailed as attachments. The website currently limits uploads to 5 MB.

## CRM later
The CRM should read the same Jobs Sheet (or this same Apps Script endpoint) using `Job ID` as the stable unique key. This avoids maintaining separate job records for website and CRM.

## Security / production notes
- The script includes a hidden honeypot field to reduce basic bot spam.
- Before high-volume launch, add stronger anti-spam/rate limiting if required.
- Do not place email passwords or Google credentials in GitHub.
- The Apps Script runs under your Google account and uses `MailApp` to send notification emails.
