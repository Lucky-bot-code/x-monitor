# X（Twitter）名人发言监控

通过 GitHub Actions 定时抓取 X (Twitter) 名人发言，检测新推文并推送到企业微信群机器人。

## 监控账号

@aleabitoreddit @binance @ChineseWSJ @cz_binance @elonmusk @EmberCN @Jackyi_ld @justinsuntron @star_okx @thankUcrypto @trumpchinese1 @X

## 工作原理

```
GitHub Actions 定时触发 (每10分钟)
    ↓
Playwright 无头 Chromium + Cookie 登录 X
    ↓
抓取每个账号最新推文
    ↓
按时间窗口过滤 (15分钟内)
    ↓
推送到企业微信 Webhook
```

## 部署 (GitHub Actions)

1. Fork 本仓库
2. 在 Settings → Secrets and variables → Actions 中添加两个 Secrets：
   - `X_AUTH_TOKEN` — X 登录后的 auth_token Cookie
   - `X_CT0` — X 登录后的 ct0 Cookie
3. Actions 每 10 分钟自动运行，无需服务器，无需本地开机

### 获取 Cookie

浏览器登录 X 后，F12 → 应用程序 → Cookies → 复制 `auth_token` 和 `ct0` 的值。

Cookie 有效期通常几周到几个月，过期后需更新 Secrets。

## 本地运行

```bash
pip install playwright httpx
python -m playwright install chromium
python run_local.py
```

`run_local.py` 支持代理（修改 `PROXY` 变量），适合本地持续运行。

## 文件说明

| 文件 | 用途 |
|------|------|
| `monitor.py` | GitHub Actions 版，一次性执行 |
| `run_local.py` | 本地版，持续循环运行，支持代理 |
| `.github/workflows/monitor.yml` | GitHub Actions 工作流配置 |

## 免费额度

公开仓库 GitHub Actions 无限免费使用。仓库保持活跃（60 天内有活动）即可避免定时任务被自动暂停。
