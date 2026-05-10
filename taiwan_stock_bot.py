"""
台股 ETF 投資早報機器人
- 抓取熱門 ETF 資料
- 抓取台股財經新聞，由 Gemini AI 篩選重要新聞
- 用 Gemini AI 分析趨勢
- 發送到 Discord
"""

import os
import yfinance as yf
import requests
import feedparser
from datetime import datetime

# ============================================================
# 設定區
# ============================================================

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")

# 追蹤的 ETF 清單
ETFS = {
    "0050 元大台灣50":          "0050.TW",
    "00878 國泰永續高股息":      "00878.TW",
    "00940 元大台灣價值高息":    "00940.TW",
    "006208 富邦台50":           "006208.TW",
    "00881 國泰台灣5G+":         "00881.TW",
    "00919 群益台灣精選高息":    "00919.TW",
    "00981A 統一台股增長":       "00981A.TW",
}

# 新聞 RSS 來源
NEWS_FEEDS = [
    "https://news.google.com/rss/search?q=台股+ETF&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=台灣股市+財經&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=台積電+聯發科+股價&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
]

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
# 抓取財經新聞
# ============================================================

def fetch_news():
    """從 RSS 抓取最新財經新聞標題"""
    news_list = []
    for feed_url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:  # 每個來源最多抓5則
                title = entry.get("title", "").strip()
                link  = entry.get("link", "")
                if title and title not in [n["title"] for n in news_list]:
                    news_list.append({"title": title, "link": link})
        except Exception as e:
            print(f"  ❌ 抓取新聞失敗：{e}")

    print(f"  📰 共抓到 {len(news_list)} 則新聞")
    return news_list

# ============================================================
# 用 Gemini AI 篩選重要新聞 + 分析 ETF
# ============================================================

def analyze_with_gemini(etf_data_list, news_list):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY 未設定！")
        return None, None

    # 整理 ETF 資料
    etf_text = ""
    for d in etf_data_list:
        etf_text += f"""
- {d['name']}（{d['symbol']}）
  現價：{d['price']} 元，漲跌：{d['change']:+.2f}（{d['change_pct']:+.2f}%）
  5日均線：{d['avg5']} 元，短期趨勢：{d['trend']}，成交量：{d['vol_ratio']}倍均量
"""

    # 整理新聞標題
    news_text = "\n".join([f"- {n['title']}" for n in news_list])

    today  = datetime.now().strftime("%Y/%m/%d")
    prompt = f"""你是一位專業的台股 ETF 分析師。以下是今日（{today}）的資料：

【ETF 數據】
{etf_text}

【今日財經新聞標題】
{news_text}

請用繁體中文完成以下兩件事：

## 任務一：篩選重要新聞
從上面的新聞標題中，挑出 3～5 則「最可能影響台股或ETF股價」的新聞。
格式如下（每則一行，前面加📌）：
📌 新聞標題

## 任務二：ETF 投資早報
根據 ETF 數據與重要新聞，撰寫簡短分析，包含：
1. 📊 今日市場概況（2句）
2. 🔥 最值得關注的 ETF（1-2支，說明原因）
3. 💡 今日建議（2句）

總字數控制在 250 字以內，風格簡潔像投資早報。"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        payload  = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=30)

        if response.status_code == 200:
            full_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]

            # 分割新聞篩選和ETF分析兩個部分
            if "## 任務二" in full_text:
                parts        = full_text.split("## 任務二")
                news_part    = parts[0].replace("## 任務一：篩選重要新聞", "").strip()
                analysis_part = parts[1].replace("：ETF 投資早報", "").strip()
            else:
                news_part     = ""
                analysis_part = full_text

            return news_part, analysis_part
        else:
            print(f"❌ Gemini API 失敗：{response.status_code} - {response.text}")
            return None, None

    except Exception as e:
        print(f"❌ Gemini API 錯誤：{e}")
        return None, None

# ============================================================
# 組合報告
# ============================================================

def build_report(etf_data_list, important_news, analysis):
    today       = datetime.now().strftime("%Y/%m/%d (%a)")
    sorted_etfs = sorted(etf_data_list, key=lambda x: x["change_pct"], reverse=True)

    lines = [
        "📰 **台股 ETF 投資早報（昨日收盤）**",
        f"📅 {today}",
        "━━━━━━━━━━━━━━━━━━━━",
        "**📊 ETF 昨日排行**",
    ]

    for d in sorted_etfs:
        arrow = "🔺" if d["change"] > 0 else ("🔻" if d["change"] < 0 else "➡️")
        lines.append(f"{arrow} {d['name']}　{d['price']}元　{d['change_pct']:+.2f}%")

    lines.append("━━━━━━━━━━━━━━━━━━━━")

    if important_news:
        lines.append("**📌 今日重要財經新聞**")
        lines.append(important_news)

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
# 發送 Discord（超過2000字自動分段）
# ============================================================

def send_discord(message):
    if not DISCORD_WEBHOOK:
        print("❌ DISCORD_WEBHOOK 未設定！")
        return False

    # Discord 單則訊息上限 2000 字，超過就分段發送
    chunks = []
    while len(message) > 1900:
        split_at = message[:1900].rfind("\n")
        if split_at == -1:
            split_at = 1900
        chunks.append(message[:split_at])
        message = message[split_at:]
    chunks.append(message)

    success = True
    for chunk in chunks:
        try:
            response = requests.post(
                DISCORD_WEBHOOK,
                json={"content": chunk},
                timeout=10,
            )
            if response.status_code != 204:
                print(f"❌ 發送失敗：{response.status_code} - {response.text}")
                success = False
        except Exception as e:
            print(f"❌ 發送錯誤：{e}")
            success = False

    if success:
        print("✅ Discord 訊息發送成功！")
    return success

# ============================================================
# 主程式
# ============================================================

def daily_job():
    print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] 開始產生投資早報...")

    print("📥 抓取 ETF 資料...")
    etf_data = collect_all_etf_data()

    print("📰 抓取財經新聞...")
    news_list = fetch_news()

    if not etf_data:
        print("❌ 無法取得任何 ETF 資料，可能是休市日")
        send_discord("📰 今日台股早報\n⚠️ 無法取得資料，今日可能為休市日。")
        return

    print("🤖 請 Gemini AI 篩選新聞 + 分析中...")
    important_news, analysis = analyze_with_gemini(etf_data, news_list)

    print("📝 組合報告...")
    report = build_report(etf_data, important_news, analysis)
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