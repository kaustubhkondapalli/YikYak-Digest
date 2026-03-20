"""
YikYak Morning Digest
Hits YikYak's internal API directly (no browser needed).
Sends a formatted digest email via Gmail SMTP.

Env vars required:
  GMAIL_USER  — your Gmail address
  GMAIL_PASS  — Gmail App Password
  TO_EMAIL    — recipient email
"""

import os, requests, smtplib, json
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Config ────────────────────────────────────────────────────────────────────
UT_LAT  = 30.2849    # UT Austin latitude
UT_LNG  = -97.7341   # UT Austin longitude
TOP_N   = 10         # posts to include
MIN_VOTES = 3

# ── Fetch posts ───────────────────────────────────────────────────────────────
def fetch_top_yaks():
    """
    YikYak serves a public hot-feed endpoint that returns posts near
    a given lat/lng. No auth required for reading.
    """
    url = "https://yikyak.com/api/fetch/v2/feed/hot"
    params = {
        "lat": UT_LAT,
        "long": UT_LNG,
        "feedType": "hot",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
        ),
        "Accept": "application/json",
        "Referer": "https://yikyak.com/",
        "Origin": "https://yikyak.com",
    }

    resp = requests.get(url, params=params, headers=headers, timeout=15)

    if resp.status_code != 200:
        print(f"⚠️  API returned {resp.status_code}. Trying fallback endpoint...")
        return fetch_fallback()

    try:
        data = resp.json()
    except json.JSONDecodeError:
        print("⚠️  Couldn't parse JSON. Trying fallback...")
        return fetch_fallback()

    # Navigate whichever nesting YikYak uses
    yaks = (
        data.get("yaks") or
        data.get("data", {}).get("yaks") or
        data.get("records") or
        (data if isinstance(data, list) else [])
    )

    posts = []
    for y in yaks:
        text  = y.get("body") or y.get("text") or y.get("message") or ""
        votes = y.get("likeCount") or y.get("voteCount") or y.get("score") or 0
        if text.strip() and votes >= MIN_VOTES:
            posts.append({"text": text.strip(), "votes": int(votes)})

    posts.sort(key=lambda x: x["votes"], reverse=True)
    return posts[:TOP_N]


def fetch_fallback():
    """Try alternate known endpoint paths."""
    endpoints = [
        f"https://yikyak.com/api/fetch/v1/feed/hot?lat={UT_LAT}&long={UT_LNG}",
        f"https://yikyak.com/api/v1/yaks?lat={UT_LAT}&lng={UT_LNG}&feed=hot",
    ]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
        ),
        "Accept": "application/json",
    }
    for url in endpoints:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                yaks = data if isinstance(data, list) else data.get("yaks", [])
                posts = []
                for y in yaks:
                    text  = y.get("body") or y.get("text") or ""
                    votes = y.get("likeCount") or y.get("score") or 0
                    if text.strip():
                        posts.append({"text": text.strip(), "votes": int(votes)})
                if posts:
                    posts.sort(key=lambda x: x["votes"], reverse=True)
                    return posts[:TOP_N]
        except Exception as e:
            print(f"Fallback {url} failed: {e}")
    return []


# ── Build email ───────────────────────────────────────────────────────────────
def build_email(posts):
    today = date.today().strftime("%A, %B %d")
    subject = f"🦬 YikYak Digest — {today}"

    plain_lines = [f"YikYak Top Posts — {today}\n{'='*40}"]
    for i, p in enumerate(posts, 1):
        votes = f"  [{p['votes']} ▲]" if p["votes"] else ""
        plain_lines.append(f"\n{i}. {p['text']}{votes}")
    plain = "\n".join(plain_lines)

    rows = ""
    for i, p in enumerate(posts, 1):
        badge = (
            f'<span style="background:#bf5700;color:#fff;padding:2px 8px;'
            f'border-radius:12px;font-size:12px;margin-left:8px">{p["votes"]} ▲</span>'
            if p["votes"] else ""
        )
        rows += f"""
        <tr style="border-bottom:1px solid #2a2a2a">
          <td style="padding:14px 8px;color:#666;font-size:13px;vertical-align:top">#{i}</td>
          <td style="padding:14px 8px;font-size:15px;line-height:1.5;color:#f0f0f0">
            {p['text']}{badge}
          </td>
        </tr>"""

    html = f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:auto;
                       background:#111;color:#f0f0f0;padding:24px">
      <h2 style="color:#bf5700;border-bottom:3px solid #bf5700;padding-bottom:8px">
        🦬 YikYak Digest &mdash; {today}
      </h2>
      <p style="color:#888;font-size:13px">Top {len(posts)} posts near UT Austin</p>
      <table style="width:100%;border-collapse:collapse">{rows}</table>
      <p style="color:#444;font-size:11px;margin-top:24px">
        Sent automatically each morning · UT Austin feed
      </p>
    </body></html>"""

    return subject, plain, html


# ── Send email ────────────────────────────────────────────────────────────────
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
        print("⚠️  No posts found — YikYak may require auth or changed their API.")
    else:
        print(f"📋 Got {len(posts)} posts. Building email...")
        subject, plain, html = build_email(posts)
        send_email(subject, plain, html)
