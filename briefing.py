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
    "tech":     "💻",
    "science":  "🔬",
    "business": "📈",
    "society":  "🌍",
    "health":   "🏥",
    "climate":  "🌿",
    "space":    "🚀",
    "other":    "✨",
}

SYSTEM_PROMPT = """You are a world briefing curator and marketing strategist. Today's date is {today}.

Search the web for TODAY's most significant breakthrough events from around the world.
Focus on: scientific discoveries, technology breakthroughs, business milestones, social movements, medical advances, climate solutions, space exploration.

STRICT SELECTION CRITERIA — only include a story if ALL of these are true:
1. It happened today or within 48 hours
2. It has clear, concrete impact on a large number of people (not niche or incremental)
3. It represents a genuine leap, not a minor update or routine announcement
4. You can articulate exactly who is affected and how

If fewer than 10 stories meet this bar today, return only the ones that do. Quality over quantity.
Never pad the list with weak or ambiguous stories.

For each story, also analyze:
- RIPPLE EFFECT: Who is concretely affected, in what order, at what scale? Think in waves — immediate / short-term / long-term.
- MARKETING LENS: Which deep human desire, fear, or social tension does this story tap into? (e.g. fear of death, desire for status, longing for belonging, anxiety about the future, desire for control, hope for fairness). Be specific and honest.

Return ONLY a JSON array (no markdown, no backticks, no preamble), up to 10 items:
[{{
  "headline": "headline in Korean (concise, punchy, under 40 chars)",
  "summary": "2-3 sentences in Korean — what exactly happened, with concrete numbers/details where available",
  "ripple": "2-3 sentences in Korean — who gets affected and how, in expanding waves. Be specific.",
  "marketing_hook": "2 sentences in Korean — which human desire/fear/tension this touches, and why it makes people stop and pay attention",
  "category": "one of: tech / science / business / society / health / climate / space / other",
  "region": "country or region in Korean (e.g. 미국, 유럽, 한국, 글로벌)"
}}]

Return ONLY the JSON array, nothing else."""


def fetch_stories(today_str: str) -> list[dict]:
    """Claude API + web search로 오늘의 브리핑 수집"""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2500,
        system=SYSTEM_PROMPT.format(today=today_str),
        messages=[{
            "role": "user",
            "content": f"Find today's ({today_str}) top world breakthroughs. Return up to 10 stories as JSON array — only include stories that clearly meet the selection criteria."
        }],
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
    )

    raw = next((b.text for b in response.content if b.type == "text"), "")
    raw = raw.strip().replace("```json", "").replace("```", "").strip()

    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"JSON 배열을 찾을 수 없습니다.\n응답 원문: {raw[:300]}")

    return json.loads(raw[start:end + 1])


def create_notion_page(stories: list[dict], today_str: str, today_display: str):
    """Notion DB에 오늘의 브리핑 페이지 생성"""
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    children = []

    # 소개 텍스트
    children.append({
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {
            "content": f"Claude가 웹 검색으로 수집한 {today_display} 세계 혁신·성공 소식 7선"
        }, "annotations": {"color": "gray"}}]}
    })
    children.append({"object": "block", "type": "divider", "divider": {}})

    # 스토리 카드
    for i, s in enumerate(stories):
        emoji = CATEGORY_EMOJI.get(s.get("category", "other"), "✨")
        region = s.get("region", "")

        # 헤드라인
        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {
                "content": f"{emoji} {s['headline']}"
            }}]}
        })

        # 지역/카테고리 태그
        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {
                "content": f"📍 {region}  |  분야: {s.get('category','').upper()}"
            }, "annotations": {"color": "gray", "italic": True}}]}
        })

        # 요약
        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {
                "content": s.get("summary", "")
            }}]}
        })

        # 파급력 (콜아웃 - 파란색)
        children.append({
            "object": "block", "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "🌊"},
                "color": "blue_background",
                "rich_text": [{"type": "text", "text": {
                    "content": f"파급력  {s.get('ripple', '')}"
                }}]
            }
        })

        # 마케팅 관점 (콜아웃 - 노란색)
        children.append({
            "object": "block", "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "🎯"},
                "color": "yellow_background",
                "rich_text": [{"type": "text", "text": {
                    "content": f"마케팅 관점  {s.get('marketing_hook', '')}"
                }}]
            }
        })

        # 구분선 (마지막 제외)
        if i < len(stories) - 1:
            children.append({"object": "block", "type": "divider", "divider": {}})

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "icon": {"type": "emoji", "emoji": "🌐"},
        "properties": {
            "Name": {
                "title": [{"type": "text", "text": {"content": f"🌐 세계 브리핑 — {today_display}"}}]
            },
            "날짜": {
                "date": {"start": today_str}
            },
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

    print(f"[{today_str}] 브리핑 생성 시작...")

    stories = fetch_stories(today_str)
    print(f"  → {len(stories)}개 스토리 수집 완료")

    page_url = create_notion_page(stories, today_str, today_display)
    print(f"  → Notion 페이지 생성 완료: {page_url}")
    print("완료!")


if __name__ == "__main__":
    main()
