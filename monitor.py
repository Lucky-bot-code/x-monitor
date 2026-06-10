"""
X (Twitter) 名人发言监控 — GitHub Actions 版
每次运行拉取最新推文，按时间窗口过滤后推送到企微

监控账号：
  - @realDonaldTrump (Trump)
  - @cz_binance (CZ Binance)
  - @aleabitoreddit (Serenity / 白毛股神)
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
from twikit import Client

# ============================================================
# 配置
# ============================================================

WECOM_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=09c77232-f5d0-4e81-b6d4-86dc078a2437"

ACCOUNTS = [
    "realDonaldTrump",
    "cz_binance",
    "aleabitoreddit",   # Serenity / 白毛股神
]

# 每次拉取每个账号的最新 N 条
FETCH_LIMIT = 10

# 只推送最近 N 分钟内的推文（留一点 buffer，防止漏推）
# GitHub Actions 每 10 分钟跑一次，buffer 设 15 分钟
LOOKBACK_MINUTES = 15

# 每轮拉取间隔（秒），避免 X 限频
FETCH_INTERVAL = 3

# 推送间隔（秒），避免企微限频
PUSH_INTERVAL = 2


def _now_utc():
    return datetime.now(timezone.utc)


def _parse_tweet_time(tweet) -> datetime | None:
    """解析 twikit tweet 的 created_at 为 UTC datetime"""
    raw = tweet.created_at
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        # epoch 秒数，twikit 返回的是 UTC epoch
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)
    if isinstance(raw, str):
        # 尝试解析常见格式
        for fmt in (
            "%a %b %d %H:%M:%S %z %Y",
            "%a %b %d %H:%M:%S +0000 %Y",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
        ):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.astimezone(timezone.utc)
            except ValueError:
                continue
    return None


def format_push_msg(account: str, name: str, text: str, created_at, url: str) -> str:
    """拼接企微 markdown 消息"""
    if len(text) > 1200:
        text = text[:1200] + "\n\n...[已截断]"

    # 转义部分 markdown 字符
    lines = []
    for line in text.split("\n"):
        if line.startswith("#"):
            line = "\\" + line
        lines.append(line)
    text = "\n".join(lines)

    beijing_time = "未知"
    t = _parse_tweet_time(created_at)
    if t:
        bj = t.astimezone(timezone(timedelta(hours=8)))
        beijing_time = bj.strftime("%Y-%m-%d %H:%M:%S") + " (北京时间)"

    return "\n".join([
        f"## {name} (@{account})",
        "",
        text,
        "",
        f"{beijing_time}",
        f"[查看原文]({url})",
    ])


def push_to_wecom(markdown: str):
    """发送 markdown 消息到企微群机器人"""
    payload = {"msgtype": "markdown", "markdown": {"content": markdown}}
    try:
        r = httpx.post(WECOM_WEBHOOK, json=payload, timeout=15)
        if r.status_code == 200:
            resp = r.json()
            if resp.get("errcode") == 0:
                print(f"  [企微] 推送成功")
            else:
                print(f"  [企微] 失败: {resp}")
        else:
            print(f"  [企微] HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  [企微] 异常: {e}")


async def fetch_tweets(client: Client, username: str) -> list:
    """拉取单个账号最新推文"""
    try:
        user = await client.get_user_by_screen_name(username)
        tweets = await user.get_tweets("Tweets", count=FETCH_LIMIT)
        return list(tweets)
    except Exception as e:
        print(f"  [错误] @{username}: {type(e).__name__}: {e}")
        return []


async def main():
    print(f"=== X 监控 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC ===\n")

    client = Client(language="en-US")
    cutoff = _now_utc() - timedelta(minutes=LOOKBACK_MINUTES)
    print(f"时间窗口: {LOOKBACK_MINUTES} 分钟 (cutoff: {cutoff.strftime('%H:%M:%S')} UTC)\n")

    total_new = 0

    for username in ACCOUNTS:
        print(f"拉取 @{username}...")
        tweets = await fetch_tweets(client, username)

        new_count = 0
        for t in tweets:
            tweet_time = _parse_tweet_time(t)
            if tweet_time and tweet_time >= cutoff:
                new_count += 1
                text = t.text or ""
                url = f"https://x.com/{username}/status/{t.id}"
                msg = format_push_msg(
                    account=username,
                    name=t.user.name,
                    text=text,
                    created_at=t.created_at,
                    url=url,
                )
                preview = text[:60].replace("\n", " ")
                print(f"  [新] {(tweet_time.strftime('%H:%M:%S') if tweet_time else '?')} | {preview}...")
                push_to_wecom(msg)
                await asyncio.sleep(PUSH_INTERVAL)

        print(f"  @{username}: {len(tweets)} 条拉取, {new_count} 条在窗口内\n")
        total_new += new_count
        await asyncio.sleep(FETCH_INTERVAL)

    print(f"=== 完成，共推送 {total_new} 条 ===\n")


if __name__ == "__main__":
    asyncio.run(main())
