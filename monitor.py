"""
X (Twitter) 名人发言监控 — RSS 版 (via xcancel.com)
每 10 分钟通过 GitHub Actions 运行，按时间窗口过滤并推送企微

监控账号：
  - @realDonaldTrump (Trump / 美股政策)
  - @cz_binance (CZ / 币圈)
  - @aleabitoreddit (Serenity / 白毛股神 / A股跨境)
"""

import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx

# ============================================================
# 配置
# ============================================================

WECOM_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=09c77232-f5d0-4e81-b6d4-86dc078a2437"

ACCOUNTS = [
    "realDonaldTrump",
    "cz_binance",
    "aleabitoreddit",   # Serenity / 白毛股神
]

# Nitter 实例列表，第一个优先，失败自动 fallback
NITTER_INSTANCES = [
    "https://xcancel.com",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]

# 每条 RSS 最多显示的推文数
RSS_LIMIT = 40

# 时间窗口（分钟）：只推最近 N 分钟内的推文
LOOKBACK_MINUTES = 15

# 企微推送之间间隔（秒）
PUSH_INTERVAL = 2


def _now_utc():
    return datetime.now(timezone.utc)


def parse_rss_date(date_str: str) -> datetime:
    """将 RSS pubDate 字符串解析为 UTC datetime"""
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        return None


def fetch_rss(username: str) -> list[dict]:
    """从 Nitter 实例拉取 RSS，返回推文列表 [{title, link, text, pub_date}]"""
    for instance in NITTER_INSTANCES:
        url = f"{instance}/{username}/rss"
        try:
            r = httpx.get(url, timeout=20, follow_redirects=True)
            if r.status_code != 200:
                print(f"  {instance} → HTTP {r.status_code}")
                continue

            root = ET.fromstring(r.text)
            items = []
            for item in root.iter("item"):
                title = item.findtext("title") or ""
                link = item.findtext("link") or ""
                description = item.findtext("description") or ""
                pub_date_str = item.findtext("pubDate") or ""
                pub_date = parse_rss_date(pub_date_str)
                items.append({
                    "title": title.strip(),
                    "link": link.strip(),
                    "text": description.strip(),
                    "pub_date": pub_date,
                })
            if items:
                print(f"  {instance} → {len(items)} 条")
                return items
            print(f"  {instance} → 空 RSS")
        except Exception as e:
            print(f"  {instance} → {e}")
            continue

    print(f"  所有 Nitter 实例均不可用")
    return []


def clean_html(text: str) -> str:
    """移除 HTML 标签"""
    import re
    return re.sub(r"<[^>]+>", "", text)


def format_push_msg(account: str, text: str, pub_date, link: str) -> str:
    """拼接企微 markdown 消息"""
    text = clean_html(text)
    if len(text) > 1200:
        text = text[:1200] + "\n\n...[已截断]"

    # 转义以 # 开头的行，防止企微 markdown 解析异常
    lines = []
    for line in text.split("\n"):
        if line.startswith("#"):
            line = "\\" + line
        lines.append(line)
    text = "\n".join(lines)

    bj_time = "未知"
    if pub_date:
        bj = pub_date.astimezone(timezone(timedelta(hours=8)))
        bj_time = bj.strftime("%Y-%m-%d %H:%M:%S") + " (北京时间)"

    return "\n".join([
        f"## @{account}",
        "",
        text,
        "",
        f"🕐 {bj_time}",
        f"[查看原文]({link})",
    ])


def push_to_wecom(markdown: str):
    """发送 markdown 消息到企微群机器人"""
    payload = {"msgtype": "markdown", "markdown": {"content": markdown}}
    try:
        r = httpx.post(WECOM_WEBHOOK, json=payload, timeout=15)
        if r.status_code == 200:
            resp = r.json()
            if resp.get("errcode") == 0:
                print(f"    [企微] OK")
            else:
                print(f"    [企微] 失败: {resp}")
        else:
            print(f"    [企微] HTTP {r.status_code}")
    except Exception as e:
        print(f"    [企微] 异常: {e}")


def main():
    print(f"=== X 名人发言监控 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC ===\n")

    cutoff = _now_utc() - timedelta(minutes=LOOKBACK_MINUTES)
    print(f"时间窗口: {LOOKBACK_MINUTES} 分钟 "
          f"(cutoff: {cutoff.strftime('%H:%M:%S')} UTC)\n")

    total_new = 0

    for username in ACCOUNTS:
        print(f"拉取 @{username}...")
        tweets = fetch_rss(username)
        new_count = 0

        for t in tweets:
            pub_date = t["pub_date"]
            if pub_date and pub_date >= cutoff:
                new_count += 1
                msg = format_push_msg(
                    account=username,
                    text=t["text"] or t["title"],
                    pub_date=pub_date,
                    link=t["link"],
                )
                preview = (t["text"] or t["title"])[:60].replace("\n", " ")
                print(f"  [新] {pub_date.strftime('%H:%M:%S') if pub_date else '?'} | {preview}...")
                push_to_wecom(msg)
                import time
                time.sleep(PUSH_INTERVAL)

        print(f"  @{username}: {len(tweets)} 条拉取, {new_count} 条在窗口内\n")
        total_new += new_count

    print(f"=== 完成，共推送 {total_new} 条 ===\n")


if __name__ == "__main__":
    main()
