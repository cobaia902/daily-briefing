import anthropic
import requests
import json
from datetime import datetime, timezone, timedelta

# ── 설정 ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = "YOUR_ANTHROPIC_API_KEY"
NOTION_API_KEY     = "YOUR_NOTION_API_KEY"
NOTION_DATABASE_ID = "YOUR_NOTION_DATABASE_ID"  # 디자인 브리핑 전용 DB

KST = timezone(timedelta(hours=9))
# ────────────────────────────────────────────────────────────────────────────

CATEGORY_EMOJI = {
    "ux":        "🧭",
    "ui":        "🎨",
    "branding":  "💠",
    "motion":    "🎬",
    "product":   "📦",
    "typography":"🔤",
    "color":     "🖍",
    "system":    "⚙️",
    "tool":      "🛠",
    "research":  "🔍",
    "other":     "✦",
}

SYSTEM_PROMPT = """You are a senior design strategist and UX/UI trend curator. Today's date is {today}.

Search the web for the most notable UX/UI and design developments from the past 48 hours.

Search across these sources and signals:
- Major product launches and redesigns (apps, websites, operating systems)
- New design tools, plugins, and feature releases (Figma, Framer, Adobe, etc.)
- Viral UI patterns or interactions circulating on X/Twitter, Dribbble, Behance
- Design research papers or case studies published by big tech (Apple, Google, Meta, etc.)
- Accessibility, motion design, typography, or color trend shifts
- UX writing, microcopy, or conversational design developments
- Design system announcements or component library updates

SELECTION CRITERIA — only include if ALL apply:
1. Happened within 48 hours OR is circulating strongly right now
2. Has clear implications for how designers or product teams should work or think
3. Is concrete enough to analyze — not vague trend-speak
4. Skip minor version bumps or routine announcements with no design significance

Return up to 10 stories. If fewer than 10 meet the bar, return only those that do.

For each story, analyze:
- DESIGN IMPLICATION: What does this mean for designers/product teams right now? What should they start doing, stop doing, or reconsider?
- PATTERN SIGNAL: What broader design shift or tension does this signal? (e.g. complexity vs simplicity, trust vs delight, speed vs craft, AI vs human authorship)

Return ONLY a JSON array (no markdown, no backticks, no preamble):
[{{
  "headline": "headline in Korean (punchy, under 40 chars)",
  "summary": "2-3 sentences in Korean — what exactly happened or was released, with concrete details",
  "design_implication": "2-3 sentences in Korean — what designers/PMs should take away and act on",
  "pattern_signal": "1-2 sentences in Korean — what bigger design tension or shift this represents",
  "category": "one of: ux / ui / branding / motion / product / typography / color / system / tool / research / other",
  "source": "source name in English (e.g. Apple, Figma, Google, Dribbble, etc.)",
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
            "content": f"Find today's ({today_str}) top UX/UI and design developments. Return up to 10 as JSON array — only include stories that meet the selection criteria."
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
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    children = []

    # 소개
    children.append({
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {
            "content": f"Claude가 웹 검색으로 수집한 {today_display} UX·UI·디자인 동향 브리핑"
        }, "annotations": {"color": "gray"}}]}
    })
    children.append({"object": "block", "type": "divider", "divider": {}})

    for i, s in enumerate(stories):
        emoji = CATEGORY_EMOJI.get(s.get("category", "other"), "✦")
        source = s.get("source", "")
        region = s.get("region", "")

        # 헤드라인
        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {
                "content": f"{emoji} {s['headline']}"
            }}]}
        })

        # 출처 / 지역 / 카테고리
        meta = f"출처: {source}" if source else ""
        if region:
            meta += f"  |  📍 {region}"
        meta += f"  |  {s.get('category','').upper()}"
        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {
                "content": meta.strip(" |")
            }, "annotations": {"color": "gray", "italic": True}}]}
        })

        # 요약
        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {
                "content": s.get("summary", "")
            }}]}
        })

        # 디자인 시사점 (보라색)
        children.append({
            "object": "block", "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "✏️"},
                "color": "purple_background",
                "rich_text": [{"type": "text", "text": {
                    "content": f"디자인 시사점  {s.get('design_implication', '')}"
                }}]
            }
        })

        # 패턴 신호 (회색)
        children.append({
            "object": "block", "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "📡"},
                "color": "gray_background",
                "rich_text": [{"type": "text", "text": {
                    "content": f"패턴 신호  {s.get('pattern_signal', '')}"
                }}]
            }
        })

        if i < len(stories) - 1:
            children.append({"object": "block", "type": "divider", "divider": {}})

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "icon": {"type": "emoji", "emoji": "🎨"},
        "properties": {
            "Name": {
                "title": [{"type": "text", "text": {"content": f"🎨 디자인 브리핑 — {today_display}"}}]
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

    print(f"[{today_str}] 디자인 브리핑 생성 시작...")

    stories = fetch_stories(today_str)
    print(f"  → {len(stories)}개 스토리 수집 완료")

    page_url = create_notion_page(stories, today_str, today_display)
    print(f"  → Notion 페이지 생성 완료: {page_url}")
    print("완료!")


if __name__ == "__main__":
    main()
