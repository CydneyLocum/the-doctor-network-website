
/**
 * The Doctor Network V5 website backend
 * Google Apps Script Web App
 *
 * 1. Create a Google Sheet named "The Doctor Network - Jobs".
 * 2. Add a tab called "Jobs" using the headers in jobs-template.csv.
 * 3. Paste the spreadsheet ID below.
 * 4. Deploy > New deployment > Web app
 *    Execute as: Me
 *    Who has access: Anyone
 * 5. Copy the /exec URL into assets/config.js on the website.
 */

const SPREADSHEET_ID = 'PASTE_YOUR_GOOGLE_SHEET_ID_HERE';
const JOBS_SHEET_NAME = 'Jobs';
const NOTIFICATION_EMAIL = 'cydney@thedoctornetwork.com.au';

function doGet(e) {
  try {
    const action = String((e && e.parameter && e.parameter.action) || 'jobs').toLowerCase();

    if (action === 'jobs') {
      const jobs = getPublishedJobs_();
      return json_({ ok: true, jobs: jobs, count: jobs.length });
    }

    if (action === 'job') {
      const id = String((e.parameter && e.parameter.id) || '').trim();
      const job = getPublishedJobs_().find(j => String(j.jobId) === id);
      if (!job) return json_({ ok: false, error: 'Opportunity not found.' });
      return json_({ ok: true, job: job });
    }

    return json_({ ok: false, error: 'Unknown action.' });
  } catch (err) {
    return json_({ ok: false, error: safeError_(err) });
  }
}

function doPost(e) {
  try {
    const p = (e && e.parameter) || {};

    // Honeypot: bots often complete hidden fields.
    if (String(p.website || '').trim()) {
      return json_({ ok: true });
    }

    const formType = String(p.formType || 'website_enquiry');
    const subject = subjectFor_(formType, p);

    const lines = [
      'The Doctor Network website submission',
      '',
      'Form: ' + formType,
      'Submitted: ' + String(p.submittedAt || new Date().toISOString()),
      'Page: ' + String(p.pageUrl || ''),
      ''
    ];

    const excluded = ['action','formType','cvBase64','cvType','cvName','website','pageUrl','submittedAt'];
    Object.keys(p).forEach(key => {
      if (excluded.indexOf(key) === -1 && String(p[key] || '').trim()) {
        lines.push(label_(key) + ': ' + String(p[key]));
      }
    });

    const attachments = [];
    if (p.cvBase64 && p.cvName) {
      const bytes = Utilities.base64Decode(String(p.cvBase64));
      const blob = Utilities.newBlob(bytes, String(p.cvType || 'application/octet-stream'), String(p.cvName));
      attachments.push(blob);
      lines.push('');
      lines.push('CV attached: ' + String(p.cvName));
    }

    const replyTo = String(p.email || '').trim();

    MailApp.sendEmail({
      to: NOTIFICATION_EMAIL,
      subject: subject,
      body: lines.join('\n'),
      replyTo: replyTo || undefined,
      attachments: attachments
    });

    return json_({ ok: true });
  } catch (err) {
    return json_({ ok: false, error: safeError_(err) });
  }
}

function getPublishedJobs_() {
  if (!SPREADSHEET_ID || SPREADSHEET_ID.indexOf('PASTE_') === 0) {
    throw new Error('Google Sheet ID has not been configured in Code.gs.');
  }

  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(JOBS_SHEET_NAME);
  if (!sheet) throw new Error('Jobs sheet not found. Expected a tab named "' + JOBS_SHEET_NAME + '".');

  const values = sheet.getDataRange().getDisplayValues();
  if (values.length < 2) return [];

  const headers = values[0].map(normalizeHeader_);
  return values.slice(1)
    .filter(row => row.some(cell => String(cell).trim() !== ''))
    .map(row => {
      const obj = {};
      headers.forEach((h, i) => obj[h] = row[i] || '');
      return obj;
    })
    .filter(j => isYes_(j.publishToWebsite) && String(j.status || '').trim().toLowerCase() === 'live')
    .map(publicJob_)
    .sort((a, b) => String(b.dateAdded || '').localeCompare(String(a.dateAdded || '')));
}

function publicJob_(j) {
  // Only return fields safe for the public website.
  return {
    jobId: j.jobId || '',
    positionTitle: j.positionTitle || '',
    specialty: j.specialty || '',
    employmentType: j.employmentType || '',
    sector: j.sector || '',
    state: j.state || '',
    location: j.location || '',
    organisationDisplay: isYes_(j.publicOrganisationName) ? (j.organisation || '') : 'Confidential',
    shortSummary: j.shortSummary || '',
    overview: j.overview || '',
    roleDetails: j.roleDetails || '',
    whyConsiderIt: j.whyConsiderIt || '',
    locationInformation: j.locationInformation || '',
    salaryRate: j.salaryRate || '',
    startDate: j.startDate || '',
    endDate: j.endDate || '',
    dateAdded: j.dateAdded || '',
    lastUpdated: j.lastUpdated || ''
  };
}

function subjectFor_(formType, p) {
  if (formType === 'doctor_registration') {
    return 'New Doctor Network registration — ' + [p.firstName, p.lastName].filter(Boolean).join(' ');
  }
  if (formType === 'employer_enquiry') {
    return 'New doctor search enquiry — ' + String(p.organisation || p.name || '');
  }
  if (formType === 'job_enquiry') {
    return 'Job enquiry — ' + String(p.jobTitle || p.jobId || 'Website opportunity');
  }
  return 'New website enquiry — ' + String(p.name || p.email || 'The Doctor Network');
}

function normalizeHeader_(value) {
  const clean = String(value || '').trim();
  const map = {
    'Job ID':'jobId',
    'Status':'status',
    'Publish to Website':'publishToWebsite',
    'Position Title':'positionTitle',
    'Specialty':'specialty',
    'Employment Type':'employmentType',
    'Sector':'sector',
    'State':'state',
    'Location':'location',
    'Organisation':'organisation',
    'Public Organisation Name?':'publicOrganisationName',
    'Short Summary':'shortSummary',
    'Overview':'overview',
    'Role Details':'roleDetails',
    'Why Consider It':'whyConsiderIt',
    'Location Information':'locationInformation',
    'Salary / Rate':'salaryRate',
    'Start Date':'startDate',
    'End Date':'endDate',
    'Contact Email':'contactEmail',
    'Date Added':'dateAdded',
    'Last Updated':'lastUpdated'
  };
  return map[clean] || clean.replace(/[^a-zA-Z0-9]+(.)/g, (_, c) => c ? c.toUpperCase() : '').replace(/^./, c => c.toLowerCase());
}

function isYes_(value) {
  return ['yes','y','true','1'].indexOf(String(value || '').trim().toLowerCase()) !== -1;
}

function label_(key) {
  return String(key).replace(/([A-Z])/g, ' $1').replace(/^./, c => c.toUpperCase());
}

function safeError_(err) {
  return err && err.message ? String(err.message) : 'Unexpected error.';
}

function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
