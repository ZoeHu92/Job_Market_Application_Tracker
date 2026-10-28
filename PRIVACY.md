# Privacy and security

**In short:**

* **Your application progress stays with you.** Ticks, dates, notes, the jobs you add and your saved filters are
  stored on your own computer. They only go elsewhere if you pick a cloud-drive folder yourself.
* **Nobody else can see it.** That includes the owner of this repository and anyone else using the tracker.
  There is no server, account or shared database, and nothing about you is uploaded.
* **The repository only holds code and public job ads.**
* **No passwords.** Member-only boards such as FMA are imported from pages you save in your own browser.

## What is stored where

| What | File | Where | Who can see it |
|---|---|---|---|
| Your ticks, dates and notes | `applications.csv` | progress folder | you |
| Jobs you added by hand or imported from saved pages (FMA, …) | `manual_jobs.csv` | progress folder | you |
| Saved sidebar filters | `preferences.json` | progress folder | you |
| Daily backups of the three files above (last 60) | `backups/` | progress folder | you |
| Read-only Excel copy for your phone | `My job applications.xlsx` | progress folder, only when it is a cloud folder | you |
| Weekly job list downloaded by the app | `latest/` | home folder | you |
| Full posting texts you opened in the app | `descriptions/` | home folder | you |
| Optional e-mail app password | `email.env` | home folder, never synced | you |
| Which folder holds your progress | `progress_folder.json` | home folder | you |
| Weekly job list, scrape report, digest text | `data/` | this GitHub repository | **public** |

**Home folder** (one per computer and user account):

| How you run the tracker | Folder |
|---|---|
| Windows (installer or zip) | `%APPDATA%\AcademicJobTracker`, e.g. `C:\Users\<you>\AppData\Roaming\AcademicJobTracker` |
| Mac | `~/Library/Application Support/AcademicJobTracker` (in Finder: *Go → Go to Folder…*) |
| From source (git clone) | `my_data/` inside the checkout; it is in `.gitignore`, so git never commits it |

The **progress folder** is the home folder unless you choose a cloud-drive folder in the app (*Data & sources →
Where your progress is stored*). It then becomes `<your cloud drive>/AcademicJobTracker`. The app always shows
the current location on that page.

**Saved pages you import** (FMA and others): the app reads the uploaded file on your computer and adds its
postings to `manual_jobs.csv`. The file itself is not kept and not sent anywhere. Do not commit saved member
pages to a public repository; the tracker never does.

## Separate for every user

* Everyone who downloads the tracker keeps their own progress on their own computer. Two people using it never
  share or see each other's data.
* On a shared computer the folders belong to your operating-system user account. Other accounts on that computer
  cannot open them, although administrators can.
* Someone who forks or downloads this repository gets the code and the public job list, never your progress.

## What is public

* This repository: the code, plus `data/` with the public job ads (title, school, deadline, salary and so on, but
  not the full posting text), the per-board scrape report and the weekly digest text.
* The weekly digest issues and the GitHub Actions run logs. They list job boards, counts and public postings,
  nothing about you or your applications.
* The repository itself sits under your GitHub account. Anyone looking at your profile can therefore tell that
  you keep a job-market tracker, though not which jobs you applied to. If you would rather hide that, see
  [Making the repository private](#making-the-repository-private).

## What the app sends over the internet

| When | To | What is sent |
|---|---|---|
| At start, if your job list is more than 7 days old | `api.github.com`, `raw.githubusercontent.com` | an ordinary download of `data/jobs.csv` |
| At start (downloaded release only) | `api.github.com` | a request for the newest version number |
| When you click *Load full posting text* or *Fetch details from this link* | that job board or school website | an ordinary page request, as if you opened the link in a browser |
| When you click *Run the scraper now* | the job boards in `config/sources.yaml` | the same requests as the weekly GitHub run |
| Optional e-mail reader, when you click *Check my e-mail alerts now* | your mail server (encrypted IMAP) | your login with the app password; the app reads the alert folder only |
| If you chose a cloud folder | your cloud-drive company, through its own app | the progress folder |

The tracker never uploads your progress. It has no analytics or usage tracking: Streamlit's usage statistics are
switched off. Requests identify themselves as "AcademicJobTracker" with a link to this repository, not with your
name. Like any web request, they carry your computer's IP address.

## Security on your computer

* **Only your computer can open the app.** The app's web page is served on `localhost`, so other devices on the
  same Wi-Fi cannot reach it. While it runs, other programs and other users logged in to the same computer could
  open the same address. On a shared computer, close the tracker window when you are done.
* **Files are plain CSV and JSON**, not encrypted by the app. Your computer login protects them. Turn on
  FileVault (Mac) or BitLocker / Device encryption (Windows) to protect them if the laptop is lost.
* **The optional e-mail password** is a Gmail *app password*, not your real password. You can revoke it at any
  time in your Google account. It is stored in `email.env`, which on Mac only your user account can read. It is
  never put in the cloud folder and never committed to git.
* **Backups:** a dated copy of your progress is saved every day (the last 60 are kept). *Data & sources → Back up
  my statuses* downloads a copy you can keep anywhere.

## Syncing through a cloud drive

* When you use a cloud folder, your progress files are stored by that company (Apple, Microsoft, Dropbox,
  Google, Nutstore) under its own privacy terms, like any other document you keep there.
* Use a folder that only you can open. Do not pick a folder you share with other people.
* Only your progress is synced. The job list, posting texts and the e-mail password stay on each computer.

## The downloads

* Every release file is built by GitHub Actions from the public source code in this repository
  (`.github/workflows/release.yml`). The release page lists each file's SHA-256 checksum.
* The files are not code-signed, because signing needs paid certificates. That is why Windows ("Windows protected
  your PC") and macOS ask for confirmation the first time you start the tracker.
* Nothing needs administrator rights. The Windows installer installs for your user account only.

## Making the repository private

You can switch the repository to private (*Settings → General → Danger zone*). Consider first:

* The job list, digest issues and run logs become private too.
* Private repositories on GitHub's free plan get 2,000 Actions minutes a month. One weekly run takes a few
  minutes, so the weekly scrape stays well within the free amount.
* The app downloads the weekly list without logging in to GitHub. For a private repository that download stops
  working, so you would refresh the list with *Data & sources → Run the scraper now* on your computer instead.
  Release downloads also need you to be logged in.
* In exchange, you may then store full posting texts (`keep_full_description: true` in
  `config/settings.yaml`), and the optional e-mail reader can also run in the weekly GitHub job.

## Removing your data

* Delete the progress folder and the home folder listed above.
* Uninstalling (Windows *Settings → Apps*), or deleting the unzipped folder, removes the program only. Your
  progress is kept on purpose, so a reinstall picks it up again.

## Reporting a problem

Open an issue in this repository. Issues are public, so do not paste your progress files, e-mail or anything
personal into them.
