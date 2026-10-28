# Academic Job Market Tracker (business schools)

A personal tracker for the business-school faculty job market (finance, accounting, marketing,
management/strategy, OB/HR, operations, information systems, analytics, business economics, real estate,
insurance and more).

* **Every Monday** a GitHub Actions job collects new postings from the job boards listed below. It saves them
  to `data/jobs.csv`. The job runs on GitHub's servers; it does not use Claude, and public repositories get it
  free.
* Each posting is parsed into **school, field, rank, tenure track, degree requirement (PhD / ABD OK), deadline,
  review start date, salary, start date, requested materials, interview venue (FMA, AFA/ASSA, …)** and the key
  requirement sentences. English and Chinese postings are both understood (截止日期, 年薪 40–80万, 助理教授,
  长聘教轨, 博士…).
* When a posting disappears from its board (or its page says *expired / filled*), it is marked **Closed**.
* A local web app lets you **tick boxes** for ⭐ shortlist → Plan to apply → Applied (date) → Interview → Flyout →
  Offer (or ✗ Out), add notes, and see deadlines coming up.
* A weekly **digest issue** opens on GitHub (GitHub emails it to you): new postings by field, deadlines in the
  next 14 days, and postings closed that week.

> 中文速览：每周一 GitHub 自动抓取 AFA、JOE、EJM、AAA、Chronicle、HigherEdJobs、THE、上海交大安泰、CES、
> 中国经济学教育科研网等网站的商学院教职；FMA、AMA、AOM、INFORMS、SSRN、listserv 等需要登录或屏蔽爬虫的来源通过
> **邮件提醒**读入（见下文 Email alerts，不需要把 FMA 密码给任何人）。双击 `start_tracker.command` (Mac) 或
> `start_tracker.bat` (Windows) 打开网页界面，打勾记录 计划投 / 已投(日期) / 面试 / Flyout / Offer。
> 你的投递记录只保存在自己电脑的 `my_data/` 文件夹里。

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
| 上海交大安泰 SJTU Antai | 师资招聘 page | department notices |
| 中国经济学教育科研网 efnchina | 招聘·教学研究 list | business/finance notices |
| Tsinghua SEM, PBCSF, SAIF | recruitment pages | tracked as one posting each, flagged 🔄 when the page changes |
| **E-mail alerts** | your mailbox (read-only) | FMA, AMA, AOM, INFORMS, AIS, jobs.ac.uk, SSRN, listservs |

All boards were checked against the live sites on 2026-10-28 (`verified:` in
[`config/sources.yaml`](config/sources.yaml)). The scraper sends an honest user agent, obeys `robots.txt`
(including crawl delays), waits between requests and never re-fetches a posting it already has.

**Not scraped, by design:** FMA's job board needs a member login. AMA, AOM, INFORMS, AIS, jobs.ac.uk and SSRN
answer automated requests with a bot challenge, and 高校人才网 disallows crawlers in its robots.txt. The tracker
does not log in with your password or try to get around these blocks. For these sources it reads the job-alert
e-mails the sites send you.

## Email alerts (FMA and the other closed boards, SSRN, listservs)

You never give anyone your FMA password: FMA sends the alerts to your inbox, and the tracker reads only that
inbox folder.

1. **Create job alerts** on each site while logged in:
   * FMA: For Job Seekers → Professional Job Board → *Create job alert* (search: all positions, or your fields).
   * AMA academic placement, AOM career center, INFORMS career center, AIS academic careers, jobs.ac.uk
     ("Jobs by Email").
   * SSRN: subscribe to the *Professional Announcements & Job Openings* e-journals of the networks you follow.
   * Listservs (AISWorld, ELMAR, AOM division lists, …): subscribe as usual.
2. **Filter them into one label.** In Gmail, create a filter (for example: from `fma.org OR ama.org OR aom.org OR
   informs.org OR aisnet.org OR jobs.ac.uk OR ssrn.com`, or list addresses) → *Apply the label* `JobAlerts`. If
   the alerts go to a university address, forward them to a Gmail account and filter there.
3. **Create an app password.** Google Account → Security → 2-Step Verification → *App passwords*. It is a
   16-character password that works only for mail access, and you can revoke it at any time.
4. **Give it to the tracker**, either:
   * **Automatic weekly reading (recommended): make this repository private** (Settings → General → Danger
     zone → Change visibility), then add two secrets under Settings → Secrets and variables → Actions:
     `TRACKER_IMAP_USER` (your Gmail address) and `TRACKER_IMAP_PASSWORD` (the app password). Secrets are
     encrypted; nobody, Claude included, can read them back. While the repository is public, the weekly run skips
     e-mail so that member-only postings are never published.
   * **Or on your own computer only:** app → *Data & sources* → *E-mail alerts* → save the address and app
     password (stored in `my_data/email.env`, never uploaded) → *Check my e-mail alerts now*.

Settings such as the label name, mail server (Outlook: `outlook.office365.com`) and look-back window are in
`config/settings.yaml` under `email:`. Alert digests become one posting per listed job; a listserv post becomes
one posting. Only business-school faculty jobs are kept.

## Using the app

| Page | What it is for |
|---|---|
| **Jobs** | All postings, soonest deadline first. Filter in the sidebar by field, rank, region, deadline window, new this week, tenure-track and PhD-level. Tick boxes save immediately. Ticking a later stage fills in the earlier ones and today's date. |
| **My applications** | Counts per stage, a to-apply list with days left (red within 7 days), and your full pipeline with editable dates. Exports to Excel. |
| **Job details** | Everything parsed for one posting, a link to the original, the full text, and a form for your progress and notes. |
| **Add a job** | Paste a link or the posting text (listserv e-mail, PDF, WeChat article) to auto-fill the form. |
| **Data & sources** | When the data was collected, which boards worked, e-mail alert setup, download / scrape buttons, Excel export and backup / restore. |

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
my_data/                   YOUR statuses, manual jobs, preferences, e-mail login, backups (local only)
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
