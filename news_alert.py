"""
台股重要新聞即時通知
每2小時檢查一次，有重要新聞才發送到 Discord
"""

import os
import requests
import feedparser
import json
from datetime import datetime

# ============================================================
# 設定區
# ============================================================

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")

# 新聞 RSS 來源
NEWS_FEEDS = [
    "https://news.google.com/rss/search?q=台股+ETF&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=台灣股市+財經&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=台積電+聯發科+股價&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
]

# 已發送過的新聞標題（避免重複發送）
SENT_CACHE_FILE = "sent_news_cache.json"

# ============================================================
# 讀取 / 儲存已發送的新聞
# ============================================================

def load_sent_cache():
    try:
        with open(SENT_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_sent_cache(cache):
    # 只保留最近 100 則，避免檔案太大
    cache = cache[-100:]
    with open(SENT_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)

# ============================================================
# 抓取新聞
# ============================================================

def fetch_news(sent_cache):
    """抓取新聞，過濾掉已發送過的"""
    news_list = []
    for feed_url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:8]:
                title = entry.get("title", "").strip()
                link  = entry.get("link", "")
                if title and title not in sent_cache and title not in [n["title"] for n in news_list]:
                    news_list.append({"title": title, "link": link})
        except Exception as e:
            print(f"  ❌ 抓取新聞失敗：{e}")

    print(f"  📰 共抓到 {len(news_list)} 則新聞（未發送過的）")
    return news_list

# ============================================================
# 用 Gemini AI 判斷是否有重要新聞
# ============================================================

def filter_important_news(news_list):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY 未設定！")
        return []

    if not news_list:
        print("  ℹ️  沒有新的新聞")
        return []

    news_text = "\n".join([f"- {n['title']}" for n in news_list])

    prompt = f"""你是一位專業的台股分析師。以下是最新的財經新聞標題：

{news_text}

請從中挑選出「真正會影響台股或ETF股價」的重要新聞，標準如下：
- 重大政策改變（升降息、關稅、法規）
- 主要企業財報或重大消息（台積電、聯發科等）
- 國際股市重大事件
- 台股大盤重要訊號

如果有重要新聞，請只列出標題，每行一則，前面加 📌。
如果沒有真正重要的新聞，只需回覆「無重要新聞」四個字，不要其他內容。"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        payload  = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=30)

        if response.status_code == 200:
            result = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f"  🤖 Gemini 回應：{result[:100]}...")

            if "無重要新聞" in result:
                return []

            # 找出有 📌 的行
            important = [line.strip() for line in result.split("\n") if "📌" in line]
            return important
        else:
            print(f"❌ Gemini API 失敗：{response.status_code}")
            return []

    except Exception as e:
        print(f"❌ Gemini API 錯誤：{e}")
        return []

# ============================================================
# 發送 Discord
# ============================================================

def send_discord(message):
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
            print(f"❌ 發送失敗：{response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 發送錯誤：{e}")
        return False

# ============================================================
# 主程式
# ============================================================

def check_news():
    now = datetime.now().strftime("%H:%M")
    print(f"\n⏰ [{now}] 檢查重要新聞中...")

    sent_cache = load_sent_cache()
    news_list  = fetch_news(sent_cache)

    print("🤖 請 Gemini AI 篩選重要新聞...")
    important_news = filter_important_news(news_list)

    if not important_news:
        print("  ℹ️  本次沒有重要新聞，不發送。")
        return

    # 組合訊息
    lines = [
        "🚨 **台股重要新聞快報**",
        f"⏰ {datetime.now().strftime('%Y/%m/%d %H:%M')}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    lines += important_news
    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        "⚠️ 僅供參考，不構成投資建議",
    ]

    message = "\n".join(lines)
    print(message)
    send_discord(message)

    # 把這次發送的新聞存進 cache
    for news in news_list:
        if any(news["title"] in n for n in important_news):
            sent_cache.append(news["title"])
    save_sent_cache(sent_cache)


if __name__ == "__main__":
    check_news()