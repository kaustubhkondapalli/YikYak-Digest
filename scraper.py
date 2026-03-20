"""
YikYak Morning Digest
Scrapes top-voted posts from yikyak.com (UT Austin feed) and
sends a formatted email via Gmail SMTP.

Env vars required:
  YIKYAK_PHONE   — your phone number (used to log in)
  GMAIL_USER     — your Gmail address
  GMAIL_PASS     — Gmail App Password (not your real password)
  TO_EMAIL       — recipient email (can be same as GMAIL_USER)
"""

import os, time, smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ── Config ────────────────────────────────────────────────────────────────────
UT_LAT, UT_LNG = 30.2849, -97.7341   # UT Austin coordinates
TOP_N          = 10                   # how many posts to include
MIN_VOTES      = 5                    # ignore posts with fewer votes

# ── Browser setup ─────────────────────────────────────────────────────────────
def make_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")
    # Spoof geolocation to UT Austin
    opts.add_experimental_option("prefs", {
        "profile.default_content_setting_values.geolocation": 1
    })
    import os
    from selenium.webdriver.chrome.service import Service
    chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/chromium-browser")
    chromedriver = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
    opts.binary_location = chrome_bin
    driver = webdriver.Chrome(service=Service(chromedriver), options=opts)
    # Override JS geolocation
    driver.execute_cdp_cmd("Emulation.setGeolocationOverride", {
        "latitude": UT_LAT, "longitude": UT_LNG, "accuracy": 50
    })
    return driver

# ── Scrape ────────────────────────────────────────────────────────────────────
def fetch_top_yaks():
    driver = make_driver()
    posts = []
    try:
        driver.get("https://yikyak.com")
        wait = WebDriverWait(driver, 20)

        # Wait for feed to load
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='yak-card'], .yak-card, article")))
        time.sleep(3)  # let vote counts render

        # Scroll a bit to load more posts
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 800)")
            time.sleep(1.5)

        # Try multiple possible selectors (YikYak updates their DOM occasionally)
        card_selectors = [
            "[data-testid='yak-card']",
            ".yak-card",
            "article[class*='yak']",
            "div[class*='YakCard']",
        ]
        cards = []
        for sel in card_selectors:
            cards = driver.find_elements(By.CSS_SELECTOR, sel)
            if cards:
                break

        if not cards:
            # Fallback: grab all text blocks paired with vote counts
            print("⚠️  Primary selectors failed, using fallback text extraction")
            return fallback_extract(driver)

        for card in cards:
            try:
                # Post text
                txt_el = card.find_element(By.CSS_SELECTOR,
                    "[data-testid='yak-text'], p, .yak-text, div[class*='message']")
                text = txt_el.text.strip()

                # Vote count
                try:
                    vote_el = card.find_element(By.CSS_SELECTOR,
                        "[data-testid='vote-count'], .vote-count, span[class*='vote'], span[class*='like']")
                    votes = int("".join(filter(str.isdigit, vote_el.text)) or "0")
                except Exception:
                    votes = 0

                if text and votes >= MIN_VOTES:
                    posts.append({"text": text, "votes": votes})
            except Exception:
                continue

    finally:
        driver.quit()

    posts.sort(key=lambda x: x["votes"], reverse=True)
    return posts[:TOP_N]


def fallback_extract(driver):
    """Last-resort: scrape all visible text and guess structure."""
    body = driver.find_element(By.TAG_NAME, "body").text
    lines = [l.strip() for l in body.splitlines() if len(l.strip()) > 20]
    # Return as plain strings without vote counts
    return [{"text": l, "votes": 0} for l in lines[:TOP_N]]


# ── Email ─────────────────────────────────────────────────────────────────────
def build_email(posts):
    today = date.today().strftime("%A, %B %d")
    subject = f"🦬 YikYak Digest — {today}"

    # Plain-text fallback
    plain_lines = [f"YikYak Top Posts — {today}\n{'='*40}"]
    for i, p in enumerate(posts, 1):
        votes = f"  [{p['votes']} votes]" if p['votes'] else ""
        plain_lines.append(f"\n{i}. {p['text']}{votes}")
    plain = "\n".join(plain_lines)

    # HTML version
    rows = ""
    for i, p in enumerate(posts, 1):
        vote_badge = (f'<span style="background:#ff5722;color:#fff;'
                      f'padding:2px 8px;border-radius:12px;font-size:12px;'
                      f'margin-left:8px">{p["votes"]} ▲</span>'
                      if p["votes"] else "")
        rows += f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:14px 8px;color:#999;font-size:13px;vertical-align:top">#{i}</td>
          <td style="padding:14px 8px;font-size:15px;line-height:1.5;color:#222">
            {p['text']}{vote_badge}
          </td>
        </tr>"""

    html = f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:auto;color:#222">
      <h2 style="color:#bf5700;border-bottom:3px solid #bf5700;padding-bottom:8px">
        🦬 YikYak Digest &mdash; {today}
      </h2>
      <p style="color:#666;font-size:13px">Top {len(posts)} posts near UT Austin</p>
      <table style="width:100%;border-collapse:collapse">{rows}</table>
      <p style="color:#aaa;font-size:11px;margin-top:24px">
        Sent automatically each morning · UT Austin feed
      </p>
    </body></html>"""

    return subject, plain, html


def send_email(subject, plain, html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = os.environ["GMAIL_USER"]
    msg["To"]      = os.environ["TO_EMAIL"]
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(os.environ["GMAIL_USER"], os.environ["GMAIL_PASS"])
        server.sendmail(os.environ["GMAIL_USER"], os.environ["TO_EMAIL"], msg.as_string())
    print(f"✅ Email sent: {subject}")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🔍 Fetching YikYak posts...")
    posts = fetch_top_yaks()
    if not posts:
        print("⚠️  No posts found. YikYak may have updated their DOM.")
    else:
        print(f"📋 Got {len(posts)} posts. Building email...")
        subject, plain, html = build_email(posts)
        send_email(subject, plain, html)
