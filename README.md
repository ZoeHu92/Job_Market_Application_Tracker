# Academic Job Market Tracker (business schools)

A personal tracker for the business-school faculty job market (finance, accounting, marketing,
management/strategy, OB/HR, operations, information systems, analytics, business economics, real estate,
insurance and more).

* **Every Monday** a GitHub Actions job collects new postings from the job boards listed below. It saves them
  to `data/jobs.csv`. The job runs on GitHub's servers; it does not use Claude, and public repositories get it
  free.
* Each posting is parsed into **school, field, rank, tenure track, degree requirement (PhD / ABD OK), deadline,
  review start date, salary, start date, requested materials, interview venue (FMA, AFA/ASSA, …)** and the key
  requirement sentences. Postings written in Chinese (Chinese university sites) are parsed too.
* When a posting disappears from its board (or its page says *expired / filled*), it is marked **Closed**.
* A local web app lets you **tick boxes** for ⭐ shortlist → Plan to apply → Applied (date) → Interview → Flyout →
  Offer (or ✗ Out), add notes, and see deadlines coming up.
* A weekly **digest issue** opens on GitHub (GitHub emails it to you): new postings by field, deadlines in the
  next 14 days, and postings closed that week.

## Quick start

1. **Install Python 3.10+** ([python.org](https://www.python.org/downloads/)) and **git**.
2. Clone this repository:
   ```bash
   git clone https://github.com/ZoeHu92/Job_Market_Application_Tracker.git
   ```
3. Double-click **`start_tracker.command`** (macOS) or **`start_tracker.bat`** (Windows).
   The first launch installs the packages (about a minute), then the tracker opens in your browser.
   Each later launch first pulls that week's job data from GitHub.

Manual alternative: `pip install -r requirements.txt`, then `streamlit run app.py`.

## Turning on the weekly scrape (one time)

1. Make sure the branch holding this code is the repository's **default branch** (Settings → General → Default
   branch). Scheduled workflows run only there.
2. Open **Actions → Weekly job scrape → Run workflow** once to fill `data/` right away. After that it runs every
   Monday.
3. To scrape twice a week during peak season, add a second `cron` line in `.github/workflows/weekly_scrape.yml`.

You can also scrape from your own computer at any time: **Data & sources → Run the scraper now** in the app.

## Job boards

| Board | How it is read | Notes |
|---|---|---|
| AFA career center | official RSS feed + posting pages | all finance postings |
| AEA JOE | official XML export | business-school / business-field listings only |
| EconJobMarket | official JSON feed | business-school / business-field ads only |
| AAA career center | official RSS feed + posting pages | faculty postings (staff jobs dropped) |
| Chronicle of Higher Education | RSS (business & management, "professor") | business-school faculty only |
| Inside Higher Ed | RSS (business & management faculty) | business-school faculty only |
| Times Higher Education unijobs | RSS (business & economics) | UK, Europe, Asia, Australia |
| HigherEdJobs | 13 business-faculty category feeds | newest 100 per category |
| AcademicJobsOnline | RSS feed | business-school listings only |
| CES (Chinese Economists Society) | job board pages | positions in China |
| SJTU Antai College of Economics and Management | faculty recruitment page | department notices |
| China Economics Education and Research Network (efnchina.com) | faculty notices list | business/finance notices |
| Tsinghua SEM, PBCSF, SAIF | recruitment pages | tracked as one posting each, flagged 🔄 when the page changes |
| **Saved pages you upload** | app → Add jobs | FMA and other member-only or bot-protected boards |

All boards were checked against the live sites on 2026-10-28 (`verified:` in
[`config/sources.yaml`](config/sources.yaml)). The scraper sends an honest user agent, obeys `robots.txt`
(including crawl delays), waits between requests and never re-fetches a posting it already has.

**Not scraped, by design:** FMA's job board needs a member login. AMA, AOM, INFORMS, AIS, jobs.ac.uk and SSRN
answer automated requests with a bot challenge, and gaoxiaojob.com disallows crawlers in its robots.txt. The
tracker does not log in with your password or try to get around these blocks. Most of their postings also appear
on the boards above; for the rest, use the saved-page import below.

## FMA and other member-only boards (no password needed)

1. Log in to FMA as usual and open the job list (*For Job Seekers → View Positions on the Professional Job
   Board*).
2. Save the page: **Ctrl+S** (Windows) or **Cmd+S** (Mac).
3. In the app, open **Add jobs** and drop the saved `.html` file(s) in. Every posting on the page is added and
   parsed. Postings already tracked from another board (for example the same job on AFA) are skipped.

Do this whenever you check FMA, for example once a week. The same works for AMA, AOM, INFORMS, AIS and
jobs.ac.uk. A single posting from a listserv e-mail or a school website can be added by pasting its link or text
on the same page.

### Advanced (optional): read job-alert e-mails automatically

If you would rather not upload pages, the tracker can read job-alert e-mails (FMA, AMA, SSRN, listservs) from one
mailbox folder. Set up job alerts on each site, add a Gmail filter that applies the label `JobAlerts`, create a
Gmail *app password* (Google Account → Security → 2-Step Verification → App passwords), and enter it in the app
under **Data & sources → Advanced**. It is stored only on your computer in `my_data/email.env`. For automatic
weekly reading on GitHub instead, make the repository private and add the secrets `TRACKER_IMAP_USER` and
`TRACKER_IMAP_PASSWORD`. The label, mail server and look-back window are set in `config/settings.yaml` under
`email:`.

## Using the app

| Page | What it is for |
|---|---|
| **Jobs** | All postings, soonest deadline first. Filter in the sidebar by field, rank, region, deadline window, new this week, tenure-track and PhD-level. Tick boxes save immediately. Ticking a later stage fills in the earlier ones and today's date. |
| **My applications** | Counts per stage, a to-apply list with days left (red within 7 days), and your full pipeline with editable dates. Exports to Excel. |
| **Job details** | Everything parsed for one posting, a link to the original, the full text, and a form for your progress and notes. |
| **Add jobs** | Import saved pages from FMA and other member-only boards, or add one posting by pasting its link or text. |
| **Data & sources** | When the data was collected, which boards worked, download / scrape buttons, Excel export, backup / restore and the optional e-mail reader. |

Click **Save as default** in the sidebar to keep your filters (for example, Finance + Entry level).

## Privacy

Your ticks, dates and notes live in `my_data/` on your computer. That folder is listed in `.gitignore` and is
never pushed; a dated copy is kept in `my_data/backups/` every day. Use **Data & sources → Back up my
statuses** to copy them elsewhere.

While the repository is public, only public job-posting data is committed, and full posting texts are not
stored (`keep_full_description: false` in `config/settings.yaml`). The app shows the extracted requirements,
links to the original, and can load the full text on demand. If you make the repository private, you can set
that option to `true`.

### How "Closed" is decided

A posting is closed only when its board was read completely in that run and the posting is gone. The scraper
then re-checks the posting's own page: a 404, a redirect, or "expired / filled" text confirms it. If 60 % or more
of a board's postings vanish at once, that is treated as a scraping problem and nothing is closed. Postings whose
deadline passed more than 90 days ago, or that have not been seen anywhere for 4 months, are also closed.
Postings that come back are re-opened.

## Files

```
app.py                     Streamlit app
tracker/                   scraper + parsing + storage (python -m tracker.scrape)
config/sources.yaml        job boards
config/settings.yaml       politeness limits, digest and e-mail options, full-text storage
data/jobs.csv              all postings ever seen (written by the weekly workflow; opens in Excel/Stata)
data/scrape_report.json    per-board results of the last run
data/weekly_digest.md      the digest text
my_data/                   YOUR statuses, added jobs, preferences, backups (local only)
```

`data/jobs.csv` loads directly into Stata (`import delimited data/jobs.csv, varnames(1) bindquote(strict)
maxquotedrows(unlimited) encoding(utf-8)`) or pandas.

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest -q
```

The tests run offline against fake boards and a fake mailbox. They cover the parsers (deadlines, salaries,
ranks, fields, degree requirements, Chinese text), every adapter, the merge/close rules, the status rules and an
app smoke test.
