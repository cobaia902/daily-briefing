import anthropic
import requests
import json
from datetime import datetime, timezone, timedelta

# ── 설정 ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = "YOUR_ANTHROPIC_API_KEY"
NOTION_API_KEY     = "YOUR_NOTION_API_KEY"
NOTION_DATABASE_ID = "YOUR_NOTION_DATABASE_ID"  # 뉴스 브리핑 전용 DB

KST = timezone(timedelta(hours=9))
# ────────────────────────────────────────────────────────────────────────────

CATEGORY_EMOJI = {
    "politics":  "🏛",
    "economy":   "📊",
    "tech":      "💻",
    "society":   "👥",
    "culture":   "🎭",
    "sports":    "⚽",
    "global":    "🌐",
    "korea":     "🇰🇷",
    "science":   "🔬",
    "other":     "📰",
}

SYSTEM_PROMPT = """You are a news curator tracking what people are actually talking about. Today is {today}, so yesterday was {yesterday}.

Search the web for yesterday's ({yesterday}) most talked-about news stories in Korea and globally.

"화제가 된" means actually trending — measured by:
- Search volume spikes (Naver, Google)
- Social media engagement (X/Twitter, Instagram, community boards like DC Inside, Naver Cafe, Reddit)
- News outlet pick-up rate
- Community reaction and discussion threads

SELECTION CRITERIA:
1. Must have happened or surfaced on {yesterday}
2. Must have generated significant public reaction — not just reported, but discussed
3. Mix Korean domestic news and global news (aim for 5-6 Korea, 4-5 global)
4. Include a range of topics — don't just pick 10 political stories
5. Skip non-stories — routine press releases, minor updates nobody cared about

For each story analyze:
- REACTION: What was the dominant public reaction? Why did people care? What emotion did it trigger (anger, hope, shock, humor, debate)?
- CONTEXT: What background do you need to understand why this blew up specifically yesterday?

Return ONLY a JSON array (no markdown, no backticks, no preamble), up to 10 items:
[{{
  "headline": "headline in Korean (clear and direct, under 45 chars)",
  "summary": "2-3 sentences in Korean — what happened, with key facts and figures",
  "reaction": "2 sentences in Korean — what the dominant public reaction was and what emotion it triggered",
  "context": "1-2 sentences in Korean — essential background to understand why this blew up",
  "category": "one of: politics / economy / tech / society / culture / sports / global / korea / science / other",
  "region": "country or region in Korean (e.g. 한국, 미국, 글로벌)",
  "buzz_level": "high / very_high / explosive"
}}]

Return ONLY the JSON array, nothing else."""

BUZZ_LABEL = {"high": "🔥 화제", "very_high": "🔥🔥 급상승", "explosive": "🔥🔥🔥 폭발적"}


def fetch_stories(today_str: str, yesterday_str: str) -> list[dict]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2500,
        system=SYSTEM_PROMPT.format(today=today_str, yesterday=yesterday_str),
        messages=[{
            "role": "user",
            "content": f"Find yesterday's ({yesterday_str}) top 10 most talked-about news stories. Return as JSON array."
        }],
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
    )

    raw = next((b.text for b in response.content if b.type == "text"), "")
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"JSON 배열을 찾을 수 없습니다.\n원문: {raw[:300]}")
    return json.loads(raw[start:end + 1])


def create_notion_page(stories: list[dict], today_str: str, yesterday_display: str, today_display: str):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    children = []

    children.append({
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {
            "content": f"{yesterday_display} 가장 많이 회자된 뉴스 10선 — {today_display} 오전 브리핑"
        }, "annotations": {"color": "gray"}}]}
    })
    children.append({"object": "block", "type": "divider", "divider": {}})

    for i, s in enumerate(stories):
        emoji = CATEGORY_EMOJI.get(s.get("category", "other"), "📰")
        buzz = BUZZ_LABEL.get(s.get("buzz_level", "high"), "🔥 화제")

        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {
                "content": f"{emoji} {s['headline']}"
            }}]}
        })

        meta = f"{buzz}  |  📍 {s.get('region','')}  |  {s.get('category','').upper()}"
        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {
                "content": meta
            }, "annotations": {"color": "gray", "italic": True}}]}
        })

        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {
                "content": s.get("summary", "")
            }}]}
        })

        # 반응 (주황색)
        children.append({
            "object": "block", "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "💬"},
                "color": "orange_background",
                "rich_text": [{"type": "text", "text": {
                    "content": f"대중 반응  {s.get('reaction', '')}"
                }}]
            }
        })

        # 맥락 (회색)
        children.append({
            "object": "block", "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "🗂"},
                "color": "gray_background",
                "rich_text": [{"type": "text", "text": {
                    "content": f"배경 맥락  {s.get('context', '')}"
                }}]
            }
        })

        if i < len(stories) - 1:
            children.append({"object": "block", "type": "divider", "divider": {}})

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "icon": {"type": "emoji", "emoji": "📰"},
        "properties": {
            "Name": {"title": [{"type": "text", "text": {"content": f"📰 뉴스 브리핑 — {yesterday_display}"}}]},
            "날짜": {"date": {"start": today_str}},
        },
        "children": children,
    }

    res = requests.post(url, headers=headers, json=payload)
    res.raise_for_status()
    return res.json().get("url", "")


def main():
    now_kst       = datetime.now(KST)
    yesterday_kst = now_kst - timedelta(days=1)

    today_str        = now_kst.strftime("%Y-%m-%d")
    yesterday_str    = yesterday_kst.strftime("%Y-%m-%d")
    today_display    = now_kst.strftime("%Y년 %m월 %d일")
    yesterday_display = yesterday_kst.strftime("%Y년 %m월 %d일")

    print(f"[{today_str}] 뉴스 브리핑 생성 시작 (대상: {yesterday_str})...")

    stories = fetch_stories(today_str, yesterday_str)
    print(f"  → {len(stories)}개 스토리 수집 완료")

    page_url = create_notion_page(stories, today_str, yesterday_display, today_display)
    print(f"  → Notion 페이지 생성 완료: {page_url}")
    print("완료!")


if __name__ == "__main__":
    main()
