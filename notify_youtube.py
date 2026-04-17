"""
LRMusic YouTube 新影片通知腳本
觸發方式：GitHub Actions 定時排程
功能：檢查雙頻道 RSS，有新影片就廣播至 LINE 所有好友
"""

import os
import json
import feedparser
import requests
from datetime import datetime, timezone, timedelta

# ── 設定區 ──────────────────────────────────────────────
CHANNELS = [
    {
        "id": "UCvTUn4Nt2uDgFZ025ZpF-9A",    # 洛莉提琴・老歌時光 @LRMusicOldies
        "name": "洛莉提琴・老歌時光",
        "emoji": "🎻",
        "day": "wednesday",
    },
    {
        "id": "UC0rTqe2RnL629827XbI60uQ",    # LRMusic Violin @LRMusicViolin
        "name": "LRMusic Violin",
        "emoji": "🎶",
        "day": "friday",
    },
]

# 幾小時內發佈的影片才算「新影片」（避免重複推播舊影片）
NEW_VIDEO_HOURS = 6

# LINE Broadcast API
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

# 已推播紀錄檔
SENT_LOG_PATH = "sent_videos.json"
# ────────────────────────────────────────────────────────


def load_sent_log() -> set:
    """載入已推播影片 ID 清單，避免重複推播"""
    if os.path.exists(SENT_LOG_PATH):
        with open(SENT_LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("sent", []))
    return set()


def save_sent_log(sent: set):
    """儲存已推播影片 ID 清單"""
    with open(SENT_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"sent": list(sent)}, f, ensure_ascii=False, indent=2)


def fetch_new_videos(channel_id: str) -> list:
    """從 YouTube RSS 抓取新影片（NEW_VIDEO_HOURS 小時內發佈）"""
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    feed = feedparser.parse(rss_url)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=NEW_VIDEO_HOURS)

    new_videos = []
    for entry in feed.entries:
        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        if published >= cutoff:
            new_videos.append({
                "id": entry.yt_videoid,
                "title": entry.title,
                "url": entry.link,
                "published": published.isoformat(),
            })
    return new_videos


def build_line_message(channel_name: str, emoji: str, video: dict) -> dict:
    """組合 LINE Flex Message（影片推播卡片）"""
    return {
        "type": "flex",
        "altText": f"{emoji} {channel_name} 新影片上線！",
        "contents": {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{emoji} 新影片上線囉！",
                        "color": "#ffffff",
                        "weight": "bold",
                        "size": "sm",
                    }
                ],
                "backgroundColor": "#b88070",
                "paddingAll": "12px",
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": channel_name,
                        "color": "#7a3820",
                        "size": "xs",
                        "weight": "bold",
                    },
                    {
                        "type": "text",
                        "text": video["title"],
                        "wrap": True,
                        "weight": "bold",
                        "size": "md",
                        "color": "#281408",
                    },
                ],
                "paddingAll": "16px",
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "action": {
                            "type": "uri",
                            "label": "立即觀看 ▶",
                            "uri": video["url"],
                        },
                        "style": "primary",
                        "color": "#b88070",
                    }
                ],
                "paddingAll": "12px",
            },
        },
    }


def broadcast_to_line(messages: list, token: str):
    """呼叫 LINE Broadcast API 廣播給所有好友"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {"messages": messages}
    resp = requests.post(LINE_BROADCAST_URL, headers=headers, json=payload, timeout=15)

    if resp.status_code == 200:
        print(f"[OK] LINE 廣播成功，共 {len(messages)} 則訊息")
    else:
        print(f"[ERROR] LINE 廣播失敗：{resp.status_code} {resp.text}")
        resp.raise_for_status()


def main():
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("環境變數 LINE_CHANNEL_ACCESS_TOKEN 未設定")

    sent = load_sent_log()
    messages_to_send = []
    newly_sent_ids = set()

    for ch in CHANNELS:
        print(f"[INFO] 檢查頻道：{ch['name']} ({ch['id']})")
        videos = fetch_new_videos(ch["id"])

        for video in videos:
            if video["id"] in sent:
                print(f"  [SKIP] 已推播過：{video['title']}")
                continue

            print(f"  [NEW] {video['title']} — {video['url']}")
            msg = build_line_message(ch["name"], ch["emoji"], video)
            messages_to_send.append(msg)
            newly_sent_ids.add(video["id"])

    if not messages_to_send:
        print("[INFO] 沒有新影片，本次不推播")
        return

    # LINE 單次廣播最多 5 則訊息
    for i in range(0, len(messages_to_send), 5):
        batch = messages_to_send[i:i + 5]
        broadcast_to_line(batch, token)

    sent.update(newly_sent_ids)
    save_sent_log(sent)
    print(f"[DONE] 推播完成，共 {len(newly_sent_ids)} 支新影片")


if __name__ == "__main__":
    main()
