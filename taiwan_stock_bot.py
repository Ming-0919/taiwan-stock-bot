"""
台股每日播報機器人
執行方式：
  - 本機：python taiwan_stock_bot.py
  - GitHub Actions：自動執行，不需要手動操作
"""

import os
import yfinance as yf
import requests
import schedule
import time
from datetime import datetime

# ============================================================
# ✏️  設定區 - 只需修改這裡
# ============================================================

# Discord Webhook 網址
# - 本機測試：填入你的 Webhook 網址（不要上傳到 GitHub！）
# - GitHub Actions：留空字串，網址從 Secrets 自動帶入
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "https://discord.com/api/webhooks/1502682689696694342/MOLz_XnWjmefztflc2-9zV7l-oQeFoPEOt72tCZWPd1WjtB8r17unjNWP3DsTiRjz5UI")

# 想追蹤的股票，格式：{"顯示名稱": "股票代號"}
STOCKS = {
    "加權指數": "^TWII",
    "台積電":   "2330",
    "聯發科":   "2454",
    "鴻海":     "2317",
    "台達電":   "2308",
}

# 本機模式：每天幾點發送（24小時制，台灣時間）
SEND_TIME = "08:30"

# ============================================================
# 功能函式（不需要修改）
# ============================================================

def get_stock_data(code: str):
    try:
        symbol = code if code.startswith("^") else f"{code}.TW"
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d")

        if hist.empty:
            print(f"  ⚠️  {code} 沒有資料（可能今天休市）")
            return None

        today_close = hist["Close"].iloc[-1]

        if len(hist) >= 2:
            yesterday_close = hist["Close"].iloc[-2]
            change = today_close - yesterday_close
            change_pct = (change / yesterday_close) * 100
        else:
            change = 0.0
            change_pct = 0.0

        return {
            "price":      round(today_close, 2),
            "change":     round(change, 2),
            "change_pct": round(change_pct, 2),
        }

    except Exception as e:
        print(f"  ❌ 抓取 {code} 失敗：{e}")
        return None


def build_report() -> str:
    today = datetime.now().strftime("%Y/%m/%d (%a)")
    lines = [
        "📊 台股每日播報",
        f"📅 {today}",
        "─────────────────",
    ]

    for name, code in STOCKS.items():
        data = get_stock_data(code)

        if data is None:
            lines.append(f"❓ {name}：無法取得資料")
            continue

        price  = data["price"]
        change = data["change"]
        pct    = data["change_pct"]
        arrow  = "🔺" if change > 0 else ("🔻" if change < 0 else "➡️")

        lines.append(f"{arrow} {name}（{code}）")
        lines.append(f"   {price}　{change:+.2f}（{pct:+.2f}%）")

    lines += [
        "─────────────────",
        "💡 資料來源：Yahoo Finance",
    ]

    return "\n".join(lines)


def send_discord(message: str) -> bool:
    if not DISCORD_WEBHOOK:
        print("❌ DISCORD_WEBHOOK 未設定！")
        return False

    try:
        response = requests.post(
            DISCORD_WEBHOOK,
            json={"content": message},
            timeout=10,
        )
        if response.status_code == 204:
            print("✅ Discord 訊息發送成功！")
            return True
        else:
            print(f"❌ 發送失敗，狀態碼：{response.status_code}")
            print(f"   回應：{response.text}")
            return False

    except requests.exceptions.Timeout:
        print("❌ 連線逾時，請檢查網路")
        return False
    except Exception as e:
        print(f"❌ 發送時發生錯誤：{e}")
        return False


def daily_job():
    print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] 開始產生報告...")
    report = build_report()
    print(report)
    send_discord(report)


# ============================================================
# 主程式入口
# ============================================================

if __name__ == "__main__":

    IS_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"

    if IS_GITHUB_ACTIONS:
        print("🤖 偵測到 GitHub Actions 環境，執行一次後結束。")
        daily_job()

    else:
        print("🚀 本機模式啟動！")
        print(f"   追蹤股票：{', '.join(STOCKS.keys())}")
        print(f"   每天發送時間：{SEND_TIME}")
        print("=" * 40)
        print("📤 先測試發送一次，確認設定正確...")
        daily_job()

        schedule.every().day.at(SEND_TIME).do(daily_job)
        print(f"\n⏳ 排程等待中（每天 {SEND_TIME} 發送），按 Ctrl+C 停止。")

        while True:
            schedule.run_pending()
            time.sleep(30)