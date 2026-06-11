"""
X (Twitter) 名人发言监控 — Playwright 版
通过 GitHub Actions 定时运行，使用无头 Chromium 抓取推文并推送企微
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx
from playwright.sync_api import sync_playwright

# ============================================================
# 配置
# ============================================================

WECOM_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=09c77232-f5d0-4e81-b6d4-86dc078a2437"

AUTH_TOKEN = os.environ.get("X_AUTH_TOKEN", "")
CT0 = os.environ.get("X_CT0", "")

COOKIES = [
    {"name": "auth_token", "value": AUTH_TOKEN, "domain": ".x.com", "path": "/"},
    {"name": "ct0", "value": CT0, "domain": ".x.com", "path": "/"},
]

PROXY = os.environ.get("X_PROXY", None)

ACCOUNTS = [
    "aleabitoreddit",
    "binance",
    "ChineseWSJ",
    "cz_binance",
    "elonmusk",
    "EmberCN",
    "Jackyi_ld",
    "justinsuntron",
    "star_okx",
    "thankUcrypto",
    "trumpchinese1",
    "X",
]

FETCH_LIMIT = 10
LOOKBACK_MINUTES = 15
PAGE_TIMEOUT = 60000
RENDER_WAIT = 5000
PUSH_INTERVAL = 2
FETCH_INTERVAL = 3

# ============================================================
# 工具函数
# ============================================================

def _now_utc():
    return datetime.now(timezone.utc)


def parse_tweet_time(time_str: str) -> datetime | None:
    if not time_str:
        return None
    now = _now_utc()
    t = time_str.strip().lower()
    try:
        if t.endswith("s") and t[:-1].isdigit():
            return now - timedelta(seconds=int(t[:-1]))
        if t.endswith("m") and t[:-1].isdigit():
            return now - timedelta(minutes=int(t[:-1]))
        if t.endswith("h") and t[:-1].isdigit():
            return now - timedelta(hours=int(t[:-1]))
        if t.endswith("d") and t[:-1].isdigit():
            return now - timedelta(days=int(t[:-1]))
    except ValueError:
        pass
    for fmt in (
        "%a %b %d %H:%M:%S %z %Y",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            dt = datetime.strptime(time_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def extract_tweets(page, username: str) -> list[dict]:
    tweets = []
    try:
        articles = page.query_selector_all('article[data-testid="tweet"]')
    except Exception:
        return tweets

    for article in articles[:FETCH_LIMIT]:
        try:
            links = article.query_selector_all('a[href*="/status/"]')
            tweet_url = ""
            tweet_id = ""
            for link in links:
                href = link.get_attribute("href") or ""
                if "/status/" in href:
                    tweet_url = "https://x.com" + href.split("?")[0]
                    parts = href.split("/status/")
                    if len(parts) > 1:
                        tweet_id = parts[1].split("?")[0].split("/")[0].strip()
                    break

            if not tweet_id:
                continue

            text = ""
            text_div = article.query_selector('[data-testid="tweetText"]')
            if text_div:
                text = text_div.text_content() or ""

            time_el = article.query_selector("time")
            datetime_str = ""
            if time_el:
                datetime_str = time_el.get_attribute("datetime") or ""

            tweets.append({
                "id": tweet_id,
                "text": text.strip(),
                "datetime": datetime_str,
                "url": tweet_url,
            })
        except Exception:
            continue

    return tweets


def format_push_msg(account: str, text: str, dt_str: str, url: str) -> str:
    if len(text) > 1200:
        text = text[:1200] + "\n\n...[已截断]"
    lines = []
    for line in text.split("\n"):
        if line.startswith("#"):
            line = "\\" + line
        lines.append(line)
    text = "\n".join(lines)

    bj = "未知"
    if dt_str:
        t = parse_tweet_time(dt_str)
        if t:
            bj = t.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S") + " (北京)"
        else:
            bj = dt_str

    return "\n".join([
        f"## @{account}",
        "",
        text,
        "",
        f"🕐 {bj}",
        f"[查看原文]({url})",
    ])


def push_to_wecom(markdown: str):
    payload = {"msgtype": "markdown", "markdown": {"content": markdown}}
    try:
        r = httpx.post(WECOM_WEBHOOK, json=payload, timeout=15)
        if r.status_code == 200:
            resp = r.json()
            if resp.get("errcode") == 0:
                print("    [企微] OK")
            else:
                print(f"    [企微] 失败: {resp}")
        else:
            print(f"    [企微] HTTP {r.status_code}")
    except Exception as e:
        print(f"    [企微] 异常: {e}")


# ============================================================
# 主逻辑
# ============================================================

def main():
    print(f"=== X 监控 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC ===\n")

    if not AUTH_TOKEN:
        print("错误: X_AUTH_TOKEN 环境变量未设置，退出")
        sys.exit(1)

    cutoff = _now_utc() - timedelta(minutes=LOOKBACK_MINUTES)
    print(f"时间窗口: {LOOKBACK_MINUTES} 分钟\n")

    with sync_playwright() as p:
        launch_kwargs = {"headless": True}
        if PROXY:
            launch_kwargs["proxy"] = {"server": PROXY}
        browser = p.chromium.launch(**launch_kwargs)
        ctx = browser.new_context(
            storage_state={"cookies": COOKIES},
            locale="en-US",
        )

        total_new = 0
        for username in ACCOUNTS:
            print(f"拉取 @{username}...", end=" ", flush=True)
            page = ctx.new_page()
            new_count = 0
            tweets = []

            for attempt in range(3):
                try:
                    page.goto(
                        f"https://x.com/{username}",
                        timeout=PAGE_TIMEOUT,
                        wait_until="domcontentloaded",
                    )
                    page.wait_for_timeout(RENDER_WAIT)
                    tweets = extract_tweets(page, username)
                    break
                except Exception as e:
                    if attempt < 2:
                        print(f"重试{attempt+1}...", end=" ", flush=True)
                        time.sleep(5)
                    else:
                        print(f"失败: {type(e).__name__}: {e}")

            for t in tweets:
                t_time = parse_tweet_time(t["datetime"])
                if t_time and t_time >= cutoff:
                    new_count += 1
                    preview = t["text"][:60].replace("\n", " ")
                    print(f"\n  [新] {(t_time.strftime('%H:%M:%S') if t_time else '?')} | {preview}...")
                    msg = format_push_msg(username, t["text"], t["datetime"], t["url"])
                    push_to_wecom(msg)
                    time.sleep(PUSH_INTERVAL)

            print(f"{len(tweets)}条拉取, {new_count}条新推送")
            page.close()
            total_new += new_count
            time.sleep(FETCH_INTERVAL)

        browser.close()
        print(f"\n=== 完成，共推送 {total_new} 条 ===")


if __name__ == "__main__":
    main()
