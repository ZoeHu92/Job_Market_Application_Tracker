# User guide

1. [Install and start](#1-install-and-start)
2. [A quick tour](#2-a-quick-tour)
3. [Tracking your applications](#3-tracking-your-applications)
4. [Your weekly routine](#4-your-weekly-routine)
5. [Adding FMA and other member-only postings](#5-adding-fma-and-other-member-only-postings)
6. [Adding a single posting](#6-adding-a-single-posting)
7. [Several computers and your phone](#7-several-computers-and-your-phone)
8. [Updating to a new version](#8-updating-to-a-new-version)
9. [Backups and restoring](#9-backups-and-restoring)
10. [Keeping the weekly scrape running](#10-keeping-the-weekly-scrape-running-repository-owner)
11. [Troubleshooting](#11-troubleshooting)

Where your data is kept, and who can see it, is explained in [PRIVACY.md](../PRIVACY.md).

## 1. Install and start

Download the file for your computer from the
**[Releases page](https://github.com/ZoeHu92/Job_Market_Application_Tracker/releases/latest)**. The download
includes its own Python, so nothing else needs to be installed, and no administrator rights are needed.

### Windows

* **Installer (recommended):** run `AcademicJobTracker-<version>-windows-setup.exe`. Windows may say
  *"Windows protected your PC"*: click **More info → Run anyway** (the installer is not code-signed). Then start
  the tracker from the Start menu: **Academic Job Market Tracker**. You can also tick "Create a desktop shortcut"
  during setup.
* **No install:** unzip `AcademicJobTracker-<version>-windows-x64.zip` (right-click → *Extract All*), open the
  folder and double-click **Start Job Tracker.bat**.

### Mac

Pick the file that matches your Mac (Apple menu → *About This Mac*): **Chip: Apple M…** →
`macos-apple-silicon.zip`; **Processor: Intel** → `macos-intel.zip`.

1. Double-click the zip in Downloads to unpack it. You can move the `AcademicJobTracker` folder anywhere, for
   example into Documents.
2. Double-click **Start Job Tracker.command**. The first time, macOS blocks it, because the app is not signed by
   Apple. Click **Done** (not *Move to Trash*).
3. Open **System Settings → Privacy & Security** and scroll down to *Security*. Next to *"Start Job
   Tracker.command" was blocked*, click **Open Anyway**, then **Open**, and enter your Mac password if asked.
4. From now on a double-click is enough.

On macOS 14 (Sonoma) or older, you can instead **right-click** the file → **Open** → **Open**.

### What you see

A small window opens (a terminal on Mac, a black console on Windows), and the tracker appears in your web browser
a few seconds later. **Keep that small window open while you use the tracker; close it to quit.** If the browser
does not open by itself, copy the address shown in the small window (for example `http://localhost:8501`) into
your browser.

## 2. A quick tour

| Page | What it is for |
|---|---|
| **Jobs** | All postings, soonest deadline first, with tick boxes for your progress. The top row shows open positions, new this week, deadlines within 14 days, closed this week, and how many you track. Choose a job under the table to see its details. |
| **My applications** | Counts per stage, a *To apply* list of starred or planned jobs with days left (red within 7 days, orange within 14), and your whole pipeline with editable dates. *Download my applications (Excel)* exports it. |
| **Job details** | Everything read from one posting (school, field, rank, tenure track, degree requirement, deadline, review date, salary, start date, requested materials, interview venue, key requirements), a link to the original, the full text on request, and a form for your progress and notes. |
| **Add jobs** | Import saved pages from FMA and other member-only boards, or add one posting from a link or pasted text. |
| **Data & sources** | When the data was collected and which boards worked, buttons to get the latest data or scrape now, where your progress is stored (cloud sync), Excel export, backup and restore. |

**Sidebar filters:** search (school, keyword, city, JEL code), field, rank, *Entry level only*, region, status
(open / recently closed / all), *Hide jobs whose deadline has passed*, *Tenure-track / research positions only*,
*PhD-level positions only*, *Posted within* N days, *Deadline within* N days, job board, and *Hide cross-posted
duplicates*. Click **Save as default** to keep your choice (for example Finance + Entry level) every time the app
opens, or **Reset** to clear it.

**Status column:** 🆕 *New* (first seen in the last 7 days), 🟢 *Open*, 🔄 *Updated* (the posting or school
recruitment page changed in the last 7 days), 🟠 *Deadline passed* (still listed, often "open until filled"), and
⚫ *Closed* (taken down from its board, or marked expired or filled).

## 3. Tracking your applications

Tick the boxes in the **Jobs** table (or on **My applications**). Changes save immediately; there is no Save
button.

| Box | Meaning | What happens when you tick it |
|---|---|---|
| ⭐ | Interested / shortlist | It shows on *My applications → To apply* |
| Plan | You plan to apply | Same |
| Applied | Application sent | *Applied on* is set to today (you can change the date) |
| Interview | First-round interview (FMA, AFA/ASSA, virtual) | *Applied* is ticked too; *Interview on* is set to today |
| Flyout | Campus visit | *Interview* and *Applied* are ticked too; the date is set to today |
| Offer | Offer received | *Applied* is ticked too; the date is set to today |
| ✗ Out | Rejected, withdrew, or search cancelled | It moves to the end of your pipeline |

* To change a date, click the date cell on **My applications** and pick another date.
* Write notes (contacts, letters needed, portal login hints, interview impressions) in the *Notes* column or on
  the **Job details** page.
* Tip: on the **Jobs** page set the sidebar *Status* filter to "All" to find a job you tracked that has since
  closed.

## 4. Your weekly routine

### What happens by itself

* **Every Monday around 12:17 UTC** (early morning in the US, evening in China), GitHub collects new postings
  from all boards, marks postings that were filled or taken down as *Closed*, and saves the list in this
  repository. This runs on GitHub's servers: your computer can be off, and it costs nothing.
* Right after that, GitHub opens a **"Job market digest" issue** in the repository and notifies you (with GitHub's
  default settings, also by e-mail). It lists new postings by field, deadlines in the next 14 days and the
  postings that closed. Last week's digest is closed automatically.
* **The next time you open the app**, it downloads the new list if your copy is more than a week old. You can
  also click **Data & sources → Get latest data from GitHub** at any time.

### What you do (about 10 minutes)

1. **Look at what is new.** Read the digest e-mail, or open the app and set the sidebar's *Posted within* to 7
   days.
2. **Add FMA postings.** Save FMA's job list page and drop it into the app (two minutes; see
   [section 5](#5-adding-fma-and-other-member-only-postings)). Do the same for AMA, AOM, INFORMS, AIS or
   jobs.ac.uk if you follow them.
3. **Triage.** Tick ⭐ or *Plan* on the jobs you want, and *Applied* once you have sent an application.
4. **Check deadlines.** Open **My applications**: the *To apply* list shows the days left for each job you
   planned.

During the busiest months (August to December) you can collect more often; see
[section 10](#10-keeping-the-weekly-scrape-running-repository-owner).

## 5. Adding FMA and other member-only postings

FMA's job board needs a member login, and some other boards block automated visits. The tracker never asks for
your password; instead, you save the job list in your own browser and the app reads that file.

1. Log in to FMA as usual and open the job list: *For Job Seekers → View Positions on the Professional Job
   Board*. If the list has several pages, or a "Load more" button, show as many postings as you can first.
2. Save the page: **Ctrl+S** (Windows) or **Cmd+S** (Mac). In Chrome, Edge or Firefox either format works
   ("Webpage, Complete" or "HTML only"); you only need the `.html` file. Safari saves a `.webarchive` by default,
   which the app cannot read: choose *Format: Page Source* instead, or use Chrome, Edge or Firefox.
3. In the app, open **Add jobs**, choose the board (FMA), drop the saved `.html` file(s) in, and click **Import
   postings**.

The app reports how many postings it found and how many were new. Postings it already has from another board
(for example the same job on AFA) are skipped. Imported postings are stored only in your progress folder, and the
saved file itself is not kept. Do this once a week, or whenever you check FMA.

## 6. Adding a single posting

For a job from a listserv e-mail, a school website or a colleague, open **Add jobs**:

* paste the posting's **link** and click *Fetch details from this link*; or
* paste the posting's **text** and click *Fill the form from this text*.

Then check the form (school, title, field, deadline) and click **Add job**. Jobs you add show *Manual* as their
board and are never closed automatically. To remove one, open it on **Job details** and click *Delete this manually added job*.

## 7. Several computers and your phone

Your progress can live in a cloud-drive folder that all your computers share.

1. Install the cloud drive's app on each computer and sign in with the same account. iCloud Drive, OneDrive,
   Dropbox, Google Drive and Nutstore are recognised automatically. If you use both a Mac and a Windows PC,
   OneDrive, Dropbox or Nutstore are the easiest.
2. On the first computer: **Data & sources → Where your progress is stored**, choose the cloud drive and click
   **☁️ Use this folder**. Your progress moves to `<cloud drive>/AcademicJobTracker`.
3. On the second computer, do the same with the same cloud drive. If that computer already had progress, the two
   are merged: for each job, the most recent change wins. The previous local files are kept in `backups/`.

Tips:

* Let the cloud drive finish syncing before you switch computers. If both computers save at nearly the same
  moment, the cloud drive may create a "conflicted copy". The app then shows a warning with a **Merge now** button.
* **Phone:** the same folder contains **My job applications.xlsx**, refreshed whenever you change something.
  Open it in the cloud drive's phone app to check your pipeline. It is read-only: make changes on a computer.
* To stop syncing on one computer, click **💻 Stop syncing**. The progress is copied back to that computer only.
* Only your progress is synced. Each computer downloads the weekly job list itself.

## 8. Updating to a new version

When a new version is out, the app shows a notice in the sidebar with a link. Download it and:

* **Windows installer:** run the new installer. It replaces the program and keeps your progress.
* **Zip (Windows or Mac):** unzip the new version and delete the old folder (repeat the first-start step on Mac).

Your progress is stored outside the program folder, so updating never touches it.

## 9. Backups and restoring

* A dated copy of your ticks (`applications-YYYY-MM-DD.csv`) and of the jobs you added
  (`manual_jobs-YYYY-MM-DD.csv`) is saved every day in the `backups` folder next to your progress. The last 60
  days are kept.
* **Data & sources → Back up my statuses (CSV)** downloads a copy that you can keep anywhere.
* **Data & sources → Restore statuses from a backup**: choose a backup file, then click *Restore this backup*.
  This replaces your current ticks, dates and notes.
* To restore the jobs you added, quit the tracker, copy a `manual_jobs-….csv` file from `backups` into the
  progress folder and rename it to `manual_jobs.csv`.
* **Data & sources → All jobs + my statuses (Excel)** exports everything, for example to share with an adviser.

## 10. Keeping the weekly scrape running (repository owner)

Normally there is **nothing to do**. The weekly scrape is a GitHub Actions workflow
(`.github/workflows/weekly_scrape.yml`) in this repository. It runs on GitHub's servers, is free for a public
repository, and does not use Claude.

* **How to tell it ran:** you get the Monday digest notification, and the **Jobs** page says *"Data from
  <date>"*. If the data is more than a week old, the app shows a warning.
* **If a Monday digest does not arrive:** open the repository's **Actions** tab → *Weekly job scrape*. A red ✗
  shows which step failed. Click **Run workflow** to try again.
* **Boards with problems:** the **Data & sources** page lists boards that failed in the last run. A failed board
  keeps all its postings (nothing is closed on a failed read) and is tried again next week. If the same board
  fails several weeks in a row, its website has probably changed. Open an issue so the scraper can be updated.
* **Run it now:** **Actions → Weekly job scrape → Run workflow** collects new postings immediately. You can enter
  board names to run only some of them.
* **More often in peak season:** add a second line under `schedule:` in `.github/workflows/weekly_scrape.yml`,
  for example `- cron: "17 12 * * 4"` for Thursdays.
* **Default branch:** scheduled workflows only run on the repository's default branch (*Settings → General →
  Default branch*). Keep the workflow file on that branch.
* **Inactivity rule:** GitHub pauses scheduled workflows in public repositories after 60 days without any
  repository activity. Each weekly run commits new data, which counts as activity, so this should not happen.
  If GitHub ever e-mails that the workflow was disabled, open **Actions → Weekly job scrape → Enable workflow**.
* **Settings:** `config/settings.yaml` controls the digest (`weekly_digest_issue`, and `digest_fields` to list
  only some fields) and the politeness limits. `config/sources.yaml` lists the boards.
* **Without GitHub:** **Data & sources → Run the scraper now** collects postings on your own computer. It takes
  a few minutes.

## 11. Troubleshooting

| Problem | What to do |
|---|---|
| Windows: "Windows protected your PC" | Click **More info → Run anyway**. It appears because the program is not code-signed. |
| Mac: "cannot be opened" / "Apple could not verify…" | See [Install and start → Mac](#mac): **System Settings → Privacy & Security → Open Anyway**. |
| Mac: no *Open Anyway* button | Try to open the file once more, then look again. If it still does not appear, open **Terminal**, type `xattr -dr com.apple.quarantine ` (with a space at the end), drag the `AcademicJobTracker` folder into the Terminal window, and press Return. Then double-click the launcher again. |
| The browser did not open | Copy the address shown in the small window (e.g. `http://localhost:8501`) into your browser. |
| "The job data is more than a week old" | **Data & sources → Get latest data from GitHub**. If that fails, see [section 10](#10-keeping-the-weekly-scrape-running-repository-owner). |
| A saved FMA page imports 0 postings | Make sure you saved the job *list* while logged in, as an `.html` file (in Safari: *Format: Page Source*). If the list sits inside a frame, open it in its own tab first and save again. |
| A conflict warning about synced files | Click **Merge now**. |
| The page looks stuck | Reload the browser tab. If that does not help, close the small window and start the tracker again. |

Something else? Open an issue in this repository. Issues are public, so do not attach your progress files or
anything personal.
