"""
台股 ETF 投資早報機器人
- 抓取熱門 ETF 資料
- 用 Gemini AI 分析趨勢
- 發送到 Discord
"""

import os
import yfinance as yf
import requests
from datetime import datetime

# ============================================================
# 設定區
# ============================================================

DISCORD_WEBHOOK  = os.environ.get("DISCORD_WEBHOOK", "")
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY", "")

# 追蹤的 ETF 清單
ETFS = {
    "0050 元大台灣50":        "0050.TW",
    "00878 國泰永續高股息":    "00878.TW",
    "00940 元大台灣價值高息":  "00940.TW",
    "006208 富邦台50":        "006208.TW",
    "00881 國泰台灣5G+":      "00881.TW",
    "00919 群益台灣精選高息":  "00919.TW",
    "00981A 統一台股增長": "00981A.TW",
}

# ============================================================
# 抓取 ETF 資料
# ============================================================

def get_etf_data(name, symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period="5d")

        if hist.empty or len(hist) < 2:
            return None

        latest     = hist["Close"].iloc[-1]
        prev       = hist["Close"].iloc[-2]
        change     = latest - prev
        change_pct = (change / prev) * 100
        avg5       = hist["Close"].mean()
        trend      = "上漲" if latest > avg5 else "下跌"
        vol_today  = hist["Volume"].iloc[-1]
        vol_avg    = hist["Volume"].mean()
        vol_ratio  = vol_today / vol_avg if vol_avg > 0 else 1

        return {
            "name":       name,
            "symbol":     symbol,
            "price":      round(latest, 2),
            "change":     round(change, 2),
            "change_pct": round(change_pct, 2),
            "trend":      trend,
            "vol_ratio":  round(vol_ratio, 2),
            "avg5":       round(avg5, 2),
        }
    except Exception as e:
        print(f"  ❌ 抓取 {symbol} 失敗：{e}")
        return None


def collect_all_etf_data():
    results = []
    for name, symbol in ETFS.items():
        print(f"  📥 抓取 {name}...")
        data = get_etf_data(name, symbol)
        if data:
            results.append(data)
    return results

# ============================================================
# 用 Gemini AI 分析
# ============================================================

def analyze_with_gemini(etf_data_list):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY 未設定！")
        return None

    data_text = ""
    for d in etf_data_list:
        data_text += f"""
- {d['name']}（{d['symbol']}）
  現價：{d['price']} 元，漲跌：{d['change']:+.2f}（{d['change_pct']:+.2f}%）
  5日均線：{d['avg5']} 元，短期趨勢：{d['trend']}
  成交量相對均量：{d['vol_ratio']}倍
"""

    today  = datetime.now().strftime("%Y/%m/%d")
    prompt = f"""你是一位專業的台股 ETF 分析師。以下是今日（{today}）台灣熱門 ETF 的數據：

{data_text}

請用繁體中文撰寫一份簡短的「ETF 投資早報」，包含：
1. 📊 今日市場概況（2-3句）
2. 🔥 最值得關注的 ETF（選1-2支，說明原因）
3. 📈 趨勢觀察（哪些有上漲動能，哪些需要觀望）
4. 💡 今日小結與建議（2-3句）

風格要簡潔易懂，像是每天早上看的投資早報。總字數控制在300字以內。"""

    try:
        url      = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload  = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=30)

        if response.status_code == 200:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        else:
            print(f"❌ Gemini API 失敗：{response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"❌ Gemini API 錯誤：{e}")
        return None

# ============================================================
# 組合報告
# ============================================================

def build_report(etf_data_list, analysis):
    today       = datetime.now().strftime("%Y/%m/%d (%a)")
    sorted_etfs = sorted(etf_data_list, key=lambda x: x["change_pct"], reverse=True)

    lines = [
        "📰 **台股 ETF 投資早報（昨日收盤）**",,
        f"📅 {today}",
        "━━━━━━━━━━━━━━━━━━━━",
        "**📊 ETF 今日排行**",
    ]

    for d in sorted_etfs:
        arrow = "🔺" if d["change"] > 0 else ("🔻" if d["change"] < 0 else "➡️")
        lines.append(f"{arrow} {d['name']}　{d['price']}元　{d['change_pct']:+.2f}%")

    lines.append("━━━━━━━━━━━━━━━━━━━━")

    if analysis:
        lines.append("**🤖 AI 分析報告**")
        lines.append(analysis)
    else:
        lines.append("⚠️ AI 分析暫時無法取得")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        "💡 資料來源：Yahoo Finance ｜ 分析：Gemini AI",
        "⚠️ 本報告僅供參考，不構成投資建議",
    ]

    return "\n".join(lines)

# ============================================================
# 發送 Discord
# ============================================================

def send_discord(message):
    if not DISCORD_WEBHOOK:
        print("❌ DISCORD_WEBHOOK 未設定！")
        return False

    if len(message) > 1900:
        message = message[:1900] + "\n...(內容過長已截斷)"

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
            print(f"❌ 發送失敗：{response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ 發送錯誤：{e}")
        return False

# ============================================================
# 主程式
# ============================================================

def daily_job():
    print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] 開始產生投資早報...")

    print("📥 抓取 ETF 資料...")
    etf_data = collect_all_etf_data()

    if not etf_data:
        print("❌ 無法取得任何 ETF 資料，可能是休市日")
        send_discord("📰 今日台股早報\n⚠️ 無法取得資料，今日可能為休市日。")
        return

    print("🤖 請 Gemini AI 分析中...")
    analysis = analyze_with_gemini(etf_data)

    print("📝 組合報告...")
    report = build_report(etf_data, analysis)
    print(report)

    send_discord(report)


if __name__ == "__main__":
    IS_GITHUB_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"

    if IS_GITHUB_ACTIONS:
        print("🤖 GitHub Actions 環境，執行一次後結束。")
        daily_job()
    else:
        print("🚀 本機測試模式")
        print("📤 立即執行一次...")
        daily_job()