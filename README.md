# The Doctor Network — image-matched website build

This version recreates the approved homepage visual direction:
- off-white editorial background
- charcoal/green typography
- coral CTA and brand accents
- correct two coral O's in “Doctor” with a smile line joining them
- working navigation and responsive mobile menu
- image-based doctor and healthcare organisation cards
- doctor/employer journeys
- software-led USP
- opportunities filter
- functional front-end forms (demo only)
- custom smiley cursor on desktop
- favicon, sitemap and robots.txt

The portrait and supporting images were cropped from the approved generated design reference to preserve the exact visual direction.

Forms are front-end demonstrations only and need to be wired to the real CRM/email/API before production launch.


## Premium v3 changes
- Animated smiley-face cursor on desktop, with subtle scale/tilt interactions.
- Scroll reveal motion with reduced-motion support.
- Refined card and navigation interactions.
- New software product showcase to make the systems/process/speed-to-market USP visually tangible.
- New long-term network journey section.


## V4
Top navigation updated to "I am a Doctor" and "We need a doctor" on desktop and mobile.


## V5 live-data architecture
- Website forms submit to a Google Apps Script endpoint and email cydney@thedoctornetwork.com.au.
- Doctor CV uploads are attached to the notification email (5 MB front-end limit).
- The Opportunities page and homepage vacancy preview load jobs from the Google Sheet via the Apps Script endpoint.
- Individual jobs use `opportunity.html?id=JOB-ID`.
- Only jobs marked Status = Live and Publish to Website = Yes appear publicly.
- The Google Sheet is designed to remain the future CRM's source of truth.
- See V5-GO-LIVE-SETUP.md for the exact deployment steps.
