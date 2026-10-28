"""E-mail alerts: digest and single-post parsing, plus the IMAP flow against a fake server."""
from datetime import date
from email.message import EmailMessage

from tracker.sources.email_alerts import EmailSource, parse_message


def digest_email() -> bytes:
    m = EmailMessage()
    m["From"] = "FMA Job Board <noreply@fma.org>"
    m["Subject"] = "Your job alert: 3 new jobs"
    m["Date"] = "Mon, 26 Oct 2026 09:00:00 -0400"
    m["Message-ID"] = "<abc@fma.org>"
    m.set_content("plain fallback")
    m.add_alternative("""<html><body><table>
      <tr><td><a href="https://jobs.example.org/job/1?utm=x">Assistant Professor of Finance</a><br>
          Example State University<br>Columbus, OH</td></tr>
      <tr><td><a href="https://jobs.example.org/job/2">Open Rank Professor of Finance</a><br>
          University of Example<br>Hong Kong</td></tr>
      <tr><td><a href="https://jobs.example.org/job/3">Accounting Manager</a><br>Example Corp</td></tr>
      <tr><td><a href="https://fma.org/unsubscribe">Unsubscribe from these alerts</a></td></tr>
    </table></body></html>""", subtype="html")
    return m.as_bytes()


def listserv_email() -> bytes:
    m = EmailMessage()
    m["From"] = "Jane Doe <jane@example.edu>"
    m["List-Id"] = "AISWorld <aisworld.lists.aisnet.org>"
    m["Subject"] = "[AISWorld] Tenure-Track Assistant Professor in Information Systems - Example University"
    m["Date"] = "Tue, 27 Oct 2026 10:00:00 -0400"
    m["Message-ID"] = "<post1@example.edu>"
    m.set_content("The College of Business at Example University invites applications for a tenure-track "
                  "Assistant Professor in Information Systems. Applications received by December 1, 2026 will "
                  "receive full consideration. Apply at https://jobs.example.edu/123")
    return m.as_bytes()


def physics_email() -> bytes:
    m = EmailMessage()
    m["From"] = "Physics Jobs <jobs@physics.example.org>"
    m["Subject"] = "Postdoc in Particle Physics"
    m.set_content("Postdoctoral position in particle physics at Example University.")
    return m.as_bytes()


def _msg(raw):
    import email
    from email.policy import default
    return email.message_from_bytes(raw, policy=default)


def test_digest_email_yields_one_job_per_listed_faculty_post():
    jobs = parse_message(_msg(digest_email()), date(2026, 10, 28))
    assert [j.title for j in jobs] == ["Assistant Professor of Finance", "Open Rank Professor of Finance"]
    assert jobs[0].source == "FMA (email)" and jobs[0].institution == "Example State University"
    assert jobs[0].url.startswith("https://jobs.example.org/job/1") and jobs[0].posted_date == "2026-10-26"


def test_listserv_post_is_one_job():
    jobs = parse_message(_msg(listserv_email()), date(2026, 10, 28))
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source == "AISWorld (email)"
    assert j.title == "Tenure-Track Assistant Professor in Information Systems - Example University"
    assert j.url == "https://jobs.example.edu/123" and "December 1, 2026" in j.description


def test_non_business_posts_are_dropped():
    assert parse_message(_msg(physics_email()), date(2026, 10, 28)) == []


class FakeIMAP:
    def __init__(self, host):
        self.host = host
        self.messages = [digest_email(), listserv_email(), physics_email()]

    def login(self, user, password):
        assert (user, password) == ("me@gmail.com", "app-password")

    def select(self, folder, readonly=False):
        assert folder == '"JobAlerts"' and readonly
        return "OK", [b"3"]

    def search(self, charset, criteria):
        assert criteria.startswith("(SINCE ")
        return "OK", [b"1 2 3"]

    def fetch(self, num, what):
        return "OK", [(b"1 (BODY[] {n}", self.messages[int(num) - 1]), b")"]

    def logout(self):
        pass


def test_imap_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACKER_IMAP_USER", "me@gmail.com")
    monkeypatch.setenv("TRACKER_IMAP_PASSWORD", "app-password")
    monkeypatch.delenv("TRACKER_PUBLIC_REPO", raising=False)
    src = EmailSource({"name": "Email"}, settings={"email": {"folder": "JobAlerts"}})
    res = src.run(set(), today=date(2026, 10, 28), imap_factory=FakeIMAP)
    assert res.ok and not res.complete and res.pages == 3
    assert len(res.jobs) == 3


def test_no_credentials_is_a_quiet_no_op(monkeypatch, tmp_path):
    monkeypatch.delenv("TRACKER_IMAP_USER", raising=False)
    monkeypatch.delenv("TRACKER_IMAP_PASSWORD", raising=False)
    src = EmailSource({"name": "Email"})
    src.env_file = tmp_path / "missing.env"
    res = src.run(set())
    assert res.ok and res.jobs == [] and "not set up" in res.notes[0]


def test_public_repo_guard(monkeypatch):
    monkeypatch.setenv("TRACKER_PUBLIC_REPO", "true")
    monkeypatch.setenv("TRACKER_IMAP_USER", "me@gmail.com")
    monkeypatch.setenv("TRACKER_IMAP_PASSWORD", "x")
    res = EmailSource({"name": "Email"}).run(set(), imap_factory=FakeIMAP)
    assert res.jobs == [] and "public" in res.notes[0]


def test_saved_board_page_import():
    from tracker.sources.email_alerts import jobs_from_saved_page
    html = """<html><head><base href="https://www.fma.org/"></head><body><ul>
      <li><a href="/jobs/101">Assistant Professor of Finance</a> <span>Example University</span> <span>Boston, MA</span></li>
      <li><a href="/jobs/102">Clinical Professor of Finance</a> <span>Example College</span></li>
      <li><a href="/login">Member Login</a></li></ul></body></html>"""
    jobs = jobs_from_saved_page(html, "FMA", today=date(2026, 10, 28))
    assert [j.title for j in jobs] == ["Assistant Professor of Finance", "Clinical Professor of Finance"]
    assert jobs[0].url == "https://www.fma.org/jobs/101" and jobs[0].source == "FMA (saved page)"
    assert jobs[0].institution == "Example University" and jobs[0].default_field == "Finance"
