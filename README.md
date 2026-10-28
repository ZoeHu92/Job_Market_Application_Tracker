# Academic Job Market Tracker (business schools)

A personal tracker for the business-school faculty job market (finance, accounting, marketing,
management/strategy, OB/HR, operations, information systems, analytics, business economics, real estate,
insurance and more).

* **Every Monday** a GitHub Actions job collects postings from the AFA and FMA job boards, AEA JOE,
  EconJobMarket, the AAA / AMA / AOM / INFORMS / AIS career centers, jobs.ac.uk, the Chronicle,
  Inside Higher Ed and AcademicJobsOnline. It saves them to `data/jobs.csv`.
* Each posting is parsed into **school, field, rank, tenure track, degree requirement (PhD / ABD OK), deadline,
  review start date, salary, start date, requested materials, interview venue (FMA, AFA/ASSA, …)** and the key
  requirement sentences.
* When a posting disappears from its board (or its page says *expired / filled*), it is marked **Closed**.
* A local web app lets you **tick boxes** for ⭐ shortlist → Plan to apply → Applied (date) → Interview → Flyout →
  Offer (or ✗ Out), add notes, and see deadlines coming up.
* A weekly **digest issue** opens on GitHub (GitHub emails it to you): new postings by field, deadlines in the
  next 14 days, and postings closed that week.

> 中文速览：每周一自动从 AFA、FMA、JOE、EJM、AAA/AMA/AOM/INFORMS/AIS 等网站抓取商学院教职，提取学校、专业、职级、
> 是否 tenure-track、博士要求、截止日、薪酬、材料要求等；岗位下架会自动标记 Closed。双击 `start_tracker.command`
> (Mac) 或 `start_tracker.bat` (Windows) 打开网页界面，打勾记录 计划投 / 已投(日期) / 面试 / Flyout / Offer。
> 你的投递记录只保存在自己电脑的 `my_data/` 文件夹里，不会上传到 GitHub。

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

1. On GitHub open **Settings → Actions → General** and check that Actions are allowed. Under *Workflow permissions*,
   *Read and write* is not required, because the workflow requests write access itself.
2. Open **Actions → Weekly job scrape → Run workflow** once to fill `data/` right away. After that it runs every
   Monday. Scheduled runs only happen on the repository's **default branch**.
3. To scrape twice a week during peak season, add a second `cron` line in `.github/workflows/weekly_scrape.yml`.

You can also scrape from your own computer at any time: **Data & sources → Run the scraper now** in the app, or
`python -m tracker.scrape --data-dir my_data/latest`.

## Using the app

| Page | What it is for |
|---|---|
| **Jobs** | All postings, soonest deadline first. Filter in the sidebar by field, rank, region, deadline window, new this week, tenure-track and PhD-level. Tick boxes save immediately. Ticking a later stage fills in the earlier ones and today's date. |
| **My applications** | Counts per stage, a to-apply list with days left (red within 7 days), and your full pipeline with editable dates. Exports to Excel. |
| **Job details** | Everything parsed for one posting, a link to the original, the full text, and a form for your progress and notes. |
| **Add a job** | Paste a link from a school website or listserv email to auto-fill the form, or type one in. |
| **Data & sources** | When the data was collected, which boards worked, the download / scrape buttons, Excel export and backup / restore. |

Click **Save as default** in the sidebar to keep your filters (for example, Finance + Entry level).

## Privacy

This repository is **public**, so only public job-posting data is committed. Your ticks, dates and notes live in
`my_data/` on your computer. That folder is listed in `.gitignore` and is never pushed; a dated copy is kept in
`my_data/backups/` every day. Use **Data & sources → Back up my statuses** to copy them elsewhere.

Full posting texts are **not** stored in the public repo (`keep_full_description: false` in
`config/settings.yaml`). The app shows the extracted requirements and links to the original, and can load the full
text on demand. If you make the repository private, you can set that option to `true`.

## Job boards

Boards are defined in [`config/sources.yaml`](config/sources.yaml). There is no per-site code: each entry gives the
listing page and/or RSS feed and a pattern for posting links. The crawler then reads schema.org *JobPosting*
data, labeled fields and the page text. To add or fix a board, edit the YAML.

* `filter: business` keeps only business-school faculty jobs. It is used for broad boards such as JOE, the
  Chronicle and jobs.ac.uk.
* The scraper sends an honest user agent, obeys `robots.txt`, waits 1.5 s between requests to a site, and
  re-fetches nothing it already knows. A weekly run is a few hundred requests in total.
* **Status:** the board URLs and link patterns were written without live access to the sites, so the
  `verified:` fields are still blank. The first run's **Data & sources** page (or `data/scrape_report.json`) shows
  which boards returned postings. A board that fails never closes its jobs.
* The **FMA** job board may require a member login; logging in is not automated. Add FMA postings with
  **Add a job** if the board is closed to the scraper.

### How "Closed" is decided

A posting is closed only when its board was read completely in that run and the posting is gone. The scraper
then re-checks the posting's own page: a 404, a redirect, or "expired / filled" text confirms it. If 60 % or more
of a board's postings vanish at once, that is treated as a scraping problem and nothing is closed. Postings whose
deadline passed more than 90 days ago are also closed. Postings that come back are re-opened.

## Files

```
app.py                     Streamlit app
tracker/                   scraper + parsing + storage (python -m tracker.scrape)
config/sources.yaml        job boards
config/settings.yaml       politeness limits, digest options, full-text storage
data/jobs.csv              all postings ever seen (written by the weekly workflow; opens in Excel/Stata)
data/scrape_report.json    per-board results of the last run
data/weekly_digest.md      the digest text
my_data/                   YOUR statuses, manual jobs, preferences, backups (local only)
```

`data/jobs.csv` loads directly into Stata (`import delimited data/jobs.csv, varnames(1) bindquote(strict)
maxquotedrows(unlimited)`) or pandas.

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest -q
```

The tests run offline against fake boards. They cover the parsers (deadlines, salaries, ranks, fields, degree
requirements), the crawler, the merge/close rules, the status rules and an app smoke test.
