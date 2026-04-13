import anthropic
import os
import requests
import json
from datetime import datetime, timezone, timedelta

# ── 설정 ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
NOTION_API_KEY     = os.environ["NOTION_API_KEY"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

KST = timezone(timedelta(hours=9))
# ────────────────────────────────────────────────────────────────────────────

CATEGORY_EMOJI = {
    "campaign":   "📣",
    "content":    "🎞",
    "social":     "📱",
    "branding":   "💠",
    "consumer":   "🧠",
    "data":       "📊",
    "ai":         "🤖",
    "viral":      "🌀",
    "collab":     "🤝",
    "strategy":   "♟",
    "other":      "✦",
}

SYSTEM_PROMPT = """You are a senior marketing strategist tracking real-time marketing intelligence. Today is {today}.

Search the web for the most significant marketing trends, campaigns, and consumer behavior signals from the past 48 hours.

Search across:
- Viral campaigns or brand moments circulating on social media (Korea and global)
- New marketing strategies or pivots announced by major brands
- Consumer behavior research or reports published recently
- Platform algorithm changes affecting marketers (Instagram, TikTok, YouTube, Naver, Kakao)
- Influencer marketing developments
- AI tools or automation changing how marketing is done
- Brand collaborations, limited drops, or cultural marketing moments
- Marketing case studies or post-mortems published by brands or agencies
- Ad industry news (creative awards, agency moves, media buy shifts)

SELECTION CRITERIA:
1. Happened or surfaced within 48 hours
2. Has clear implications for how marketers should think or act
3. Concrete enough to analyze — not vague "marketing is changing" statements
4. Represents something a smart marketer would want to know today

For each item analyze:
- WHAT WORKED (OR DIDN'T): What was the specific mechanism — why did this campaign land, why did consumers respond this way, what made this strategy effective or not?
- STEAL THIS: What is the one actionable insight or tactic that another brand/marketer could adapt from this?

Return ONLY a JSON array (no markdown, no backticks, no preamble), up to 10 items:
[{{
  "headline": "headline in Korean (punchy, specific, under 45 chars)",
  "summary": "2-3 sentences in Korean — what exactly happened, with brand names and concrete details",
  "mechanism": "2-3 sentences in Korean — the specific reason this worked or didn't. What psychological or behavioral trigger was activated?",
  "steal_this": "1-2 sentences in Korean — the one tactic or insight another marketer could adapt right now",
  "category": "one of: campaign / content / social / branding / consumer / data / ai / viral / collab / strategy / other",
  "brand": "brand or company name (English OK)",
  "region": "country or region in Korean"
}}]

Return ONLY the JSON array, nothing else."""


def fetch_stories(today_str: str) -> list[dict]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2500,
        system=SYSTEM_PROMPT.format(today=today_str),
        messages=[{
            "role": "user",
            "content": f"Find today's ({today_str}) top marketing trends and campaigns. Return up to 10 as JSON array — only include items that clearly meet the selection criteria."
        }],
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
    )

    raw = next((b.text for b in response.content if b.type == "text"), "")
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"JSON 배열을 찾을 수 없습니다.\n원문: {raw[:300]}")
    return json.loads(raw[start:end + 1])


def create_notion_page(stories: list[dict], today_str: str, today_display: str):
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
            "content": f"Claude가 웹 검색으로 수집한 {today_display} 마케팅 트렌드 & 캠페인 인텔리전스"
        }, "annotations": {"color": "gray"}}]}
    })
    children.append({"object": "block", "type": "divider", "divider": {}})

    for i, s in enumerate(stories):
        emoji = CATEGORY_EMOJI.get(s.get("category", "other"), "✦")
        brand  = s.get("brand", "")
        region = s.get("region", "")

        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {
                "content": f"{emoji} {s['headline']}"
            }}]}
        })

        meta_parts = []
        if brand:  meta_parts.append(f"브랜드: {brand}")
        if region: meta_parts.append(f"📍 {region}")
        meta_parts.append(s.get("category", "").upper())
        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {
                "content": "  |  ".join(meta_parts)
            }, "annotations": {"color": "gray", "italic": True}}]}
        })

        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {
                "content": s.get("summary", "")
            }}]}
        })

        # 작동 원리 (초록색)
        children.append({
            "object": "block", "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "⚙️"},
                "color": "green_background",
                "rich_text": [{"type": "text", "text": {
                    "content": f"왜 통했나  {s.get('mechanism', '')}"
                }}]
            }
        })

        # 훔쳐라 (분홍색)
        children.append({
            "object": "block", "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "💡"},
                "color": "pink_background",
                "rich_text": [{"type": "text", "text": {
                    "content": f"바로 써먹기  {s.get('steal_this', '')}"
                }}]
            }
        })

        if i < len(stories) - 1:
            children.append({"object": "block", "type": "divider", "divider": {}})

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "icon": {"type": "emoji", "emoji": "📣"},
        "properties": {
            "Name": {"title": [{"type": "text", "text": {"content": f"📣 마케팅 트렌드 — {today_display}"}}]},
            "날짜": {"date": {"start": today_str}},
        },
        "children": children,
    }

    res = requests.post(url, headers=headers, json=payload)
    res.raise_for_status()
    return res.json().get("url", "")


def main():
    now_kst = datetime.now(KST)
    today_str     = now_kst.strftime("%Y-%m-%d")
    today_display = now_kst.strftime("%Y년 %m월 %d일")

    print(f"[{today_str}] 마케팅 트렌드 브리핑 생성 시작...")

    stories = fetch_stories(today_str)
    print(f"  → {len(stories)}개 아이템 수집 완료")

    page_url = create_notion_page(stories, today_str, today_display)
    print(f"  → Notion 페이지 생성 완료: {page_url}")
    print("완료!")


if __name__ == "__main__":
    main()
