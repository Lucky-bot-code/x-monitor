# X（Twitter）名人发言监控

通过 Playwright 无头浏览器 + Cookie 登录 X，定时抓取名人发言，检测新推文并推送到企业微信群机器人。纯本地运行，无需 GitHub Actions。

## 监控账号

@aleabitoreddit @binance @ChineseWSJ @cz_binance @elonmusk @EmberCN @Jackyi_ld @justinsuntron @star_okx @thankUcrypto @trumpchinese1 @X

## 工作原理

```
本地常驻进程
    ↓
Playwright 无头 Chromium + Cookie 登录 X
    ↓
每 2 分钟轮询抓取每个账号最新推文
    ↓
按时间窗口过滤 (15分钟内)
    ↓
推送到企业微信 Webhook
```

## 本地运行

```bash
pip install playwright httpx
python -m playwright install chromium
python run_local.py
```

按 `Ctrl+C` 停止。

`run_local.py` 内置代理配置（`PROXY` 变量），默认 `http://127.0.0.1:10810`，可按需修改或设为空字符串关闭。

## Cookie 配置

`run_local.py` 内已嵌入 `auth_token` 和 `ct0` Cookie。Cookie 过期时，浏览器登录 X 后 F12 → 应用程序 → Cookies → 复制新值替换即可。

## 文件说明

| 文件 | 用途 |
|------|------|
| `run_local.py` | 主程序，持续循环运行，Playwright + 企微推送 |
