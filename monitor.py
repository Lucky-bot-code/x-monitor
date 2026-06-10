"""
X (Twitter) 名人发言监控 — twikit Cookie 登录版
每 10 分钟通过 GitHub Actions 运行，按时间窗口过滤并推送企微

监控账号：
  - @realDonaldTrump (Trump / 美股政策)
  - @cz_binance (CZ / 币圈)
  - @aleabitoreddit (Serenity / 白毛股神 / A股跨境)
"""

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

import httpx
from twikit import Client
from twikit.x_client_transaction.transaction import ClientTransaction

# ============================================================
# 配置
# ============================================================

WECOM_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=09c77232-f5d0-4e81-b6d4-86dc078a2437"

AUTH_TOKEN = os.environ.get("X_AUTH_TOKEN", "")
CT0 = os.environ.get("X_CT0", "")
COOKIES = {"auth_token": AUTH_TOKEN, "ct0": CT0}

ACCOUNTS = [
    "realDonaldTrump",
    "cz_binance",
    "aleabitoreddit",
]

FETCH_LIMIT = 10
LOOKBACK_MINUTES = 15
FETCH_INTERVAL = 3
PUSH_INTERVAL = 2


# ============================================================
# Monkey-patch: 让 twikit 初始化 ClientTransaction 时携带 cookie
# 原逻辑：备份 cookie → 以游客身份请求首页 → 还原 cookie
# 问题：GitHub Actions 的游客请求被 X 拦截 → 首页加载失败 → 加密密钥提取失败
# 修复：跳过备份，直接携带 cookie 请求首页（X 返回正常登录后页面）
# ============================================================

_patched = False


def _apply_patch():
    global _patched
    if _patched:
        return
    _patched = True

    _orig = Client.request

    @wraps(_orig)
    async def _patched_request(self, method, url, auto_unlock=True,
                               raise_exception=True, **kwargs):
        headers = kwargs.pop('headers', {})

        if not self.client_transaction.home_page_response:
            ct_headers = {
                'Accept-Language': f'{self.language},{self.language.split("-")[0]};q=0.9',
                'Cache-Control': 'no-cache',
                'Referer': 'https://x.com',
                'User-Agent': self._user_agent,
            }
            # 关键修改：不备份/清空 cookie，直接带着 cookie 做 init
            await self.client_transaction.init(self.http, ct_headers)

        tid = self.client_transaction.generate_transaction_id(
            method=method, path=urlparse(url).path)
        headers['x-client-transaction-id'] = tid

        kwargs['headers'] = headers
        kwargs['auto_unlock'] = auto_unlock
        kwargs['raise_exception'] = raise_exception
        return await _orig(self, method, url, **kwargs)

    Client.request = _patched_request


# ============================================================
# 工具函数
# ============================================================

def _now_utc():
    return datetime.now(timezone.utc)


def _parse_tweet_time(tweet) -> datetime | None:
    raw = tweet.created_at
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    if isinstance(raw, datetime):
        return raw.astimezone(timezone.utc) if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        for fmt in (
            "%a %b %d %H:%M:%S %z %Y",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
        ):
            try:
                return datetime.strptime(raw, fmt).astimezone(timezone.utc)
            except ValueError:
                continue
    return None


def format_push_msg(account: str, name: str, text: str, created_at, url: str) -> str:
    if len(text) > 1200:
        text = text[:1200] + "\n\n...[已截断]"
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
        f"🕐 {beijing_time}",
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


async def fetch_tweets(client: Client, username: str) -> list:
    try:
        user = await client.get_user_by_screen_name(username)
        tweets = await user.get_tweets("Tweets", count=FETCH_LIMIT)
        return list(tweets)
    except Exception as e:
        print(f"  [错误] @{username}: {type(e).__name__}: {e}")
        return []


# ============================================================
# 主逻辑
# ============================================================

async def main():
    print(f"=== X 监控 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC ===\n")

    if not AUTH_TOKEN:
        print("错误: X_AUTH_TOKEN 环境变量未设置，退出")
        return

    _apply_patch()
    print("monkey-patch 已应用")

    client = Client(language="en-US")
    client.set_cookies(COOKIES)
    print(f"已设置 cookie: auth_token={'***' if AUTH_TOKEN else '无'}, ct0={'***' if CT0 else '无'}")

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
                    account=username, name=t.user.name, text=text,
                    created_at=t.created_at, url=url,
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
