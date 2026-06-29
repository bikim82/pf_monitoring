"""
Agent 2 — Summarizer
raw_content.json → intel_cards.json
Gemini 2.5 Flash로 자막 분석, CEO별 인텔리전스 카드 생성
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import types

# ── 경로
ROOT         = Path(__file__).parent.parent
DATA_DIR     = ROOT / "data"
RAW_INPUT    = DATA_DIR / "raw_content.json"
CARDS_OUTPUT = DATA_DIR / "intel_cards.json"

# ── 설정
MODEL                = "gemini-2.5-flash"
MAX_TRANSCRIPT_CHARS = 14000
MAX_OUTPUT_TOKENS    = 800

SYSTEM_PROMPT = """You are a senior AI infrastructure and semiconductor investment analyst at a Korean asset management firm.

Extract structured investment intelligence from CEO interviews. Focus on signals relevant to:
- AI compute demand (GPU, training/inference)
- Memory (HBM, DRAM, NAND) supply/demand
- Networking (Ethernet, InfiniBand, switches)
- Power and cooling infrastructure
- Capex plans and data center buildout

Be precise and evidence-based. Only extract what is explicitly stated in the content.
Return ONLY valid JSON, no markdown, no explanation."""


# ────────────────────────────────────────────
#  프롬프트 빌더
# ────────────────────────────────────────────

def build_prompt(item: dict) -> str:
    person   = item["person"]
    company  = item["company"]
    title    = item.get("title", "")
    channel  = item.get("channel", "")
    pub_time = item.get("published_time", "")

    raw_text = item.get("transcript") or item.get("description") or ""
    content  = raw_text[:MAX_TRANSCRIPT_CHARS]
    if len(raw_text) > MAX_TRANSCRIPT_CHARS:
        content += "\n[truncated]"

    content_type = "TRANSCRIPT" if item.get("has_transcript") else "DESCRIPTION ONLY"

    return f"""Analyze this {content_type} from {person} (CEO of {company}).

VIDEO: "{title}"
CHANNEL: {channel}
PUBLISHED: {pub_time}

{content_type}:
{content}

Return ONLY this JSON structure:
{{
  "person": "{person}",
  "company": "{company}",
  "video_id": "{item.get('id', '')}",
  "video_title": "{title}",
  "source_url": "{item.get('url', '')}",
  "published_time": "{pub_time}",
  "sentiment": "bullish or neutral or bearish",
  "sentiment_score": 0.0,
  "key_quotes": ["exact quote from content", "..."],
  "capex_signal": "what they said about capex/spending, or null",
  "bottleneck_mentioned": ["HBM", "CoWoS", "power", "..."],
  "demand_outlook": "what they said about AI demand, or null",
  "supply_concern": "any supply constraint mentioned, or null",
  "new_product_signal": "any new product/roadmap hint, or null",
  "competitor_mention": "any mention of competitors, or null",
  "macro_risk": "any risk factors mentioned, or null",
  "urgency": "high or medium or low",
  "content_quality": "full_transcript or description_only",
  "summary_ko": "3줄 이내 한국어 핵심 요약"
}}"""


# ────────────────────────────────────────────
#  Gemini API 호출
# ────────────────────────────────────────────

def call_gemini(client: genai.Client, item: dict) -> dict | None:
    prompt = build_prompt(item)
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                temperature=0.2,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        raw = response.text.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        card = json.loads(raw)
        card["analyzed_at"]    = datetime.now(timezone.utc).isoformat()
        card["input_tokens"]   = response.usage_metadata.prompt_token_count or 0
        card["output_tokens"]  = response.usage_metadata.candidates_token_count or 0
        return card

    except json.JSONDecodeError as e:
        print(f"    [JSON 파싱 실패] {e}")
        print(f"    Raw: {raw[:200]}")
        return None
    except Exception as e:
        print(f"    [API 오류] {e}")
        return None


# ────────────────────────────────────────────
#  이미 처리된 video_id 추적
# ────────────────────────────────────────────

def load_existing_cards() -> tuple[list, set]:
    if not CARDS_OUTPUT.exists():
        return [], set()
    data = json.loads(CARDS_OUTPUT.read_text(encoding="utf-8"))
    cards = data.get("cards", [])
    processed = {c["video_id"] for c in cards if c.get("video_id")}
    return cards, processed


# ────────────────────────────────────────────
#  메인
# ────────────────────────────────────────────

def run(new_items: list | None = None) -> list:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*55}")
    print(f" [Summarizer] 시작: {now_str}")
    print(f"{'='*55}")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    client = genai.Client(api_key=api_key)

    if new_items is not None:
        items_to_process = new_items
        print(f" Agent 1에서 전달받은 신규 항목: {len(items_to_process)}건")
    else:
        if not RAW_INPUT.exists():
            print(" raw_content.json 없음 — 종료")
            return []
        raw = json.loads(RAW_INPUT.read_text(encoding="utf-8"))
        items_to_process = raw.get("items", [])
        print(f" raw_content.json 전체 처리: {len(items_to_process)}건")

    existing_cards, processed_ids = load_existing_cards()
    pending = [it for it in items_to_process if it.get("id") not in processed_ids]
    print(f" 신규 분석 대상: {len(pending)}건")

    if not pending:
        print(" 처리할 신규 항목 없음")
        return existing_cards

    new_cards = []
    total_in, total_out = 0, 0

    for i, item in enumerate(pending, 1):
        title  = item.get("title", "")[:55]
        person = item.get("person", "")
        has_t  = "자막O" if item.get("has_transcript") else "자막X"
        print(f"\n  [{i}/{len(pending)}] {person} | {has_t} | {title}")

        card = call_gemini(client, item)
        if card:
            new_cards.append(card)
            total_in  += card.get("input_tokens", 0)
            total_out += card.get("output_tokens", 0)
            print(f"    sentiment={card['sentiment']} urgency={card['urgency']}")
            print(f"    요약: {card.get('summary_ko', '')}")
        else:
            print(f"    [스킵] 분석 실패")

    all_cards = (existing_cards + new_cards)[-200:]
    output = {
        "last_updated":       datetime.now(timezone.utc).isoformat(),
        "total_cards":        len(all_cards),
        "new_cards_this_run": len(new_cards),
        "cards":              all_cards,
    }
    CARDS_OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cost = total_in * 0.075 / 1_000_000 + total_out * 0.30 / 1_000_000
    print(f"\n{'='*55}")
    print(f" [완료] 신규 카드 {len(new_cards)}장")
    print(f" 토큰 사용: input {total_in:,} / output {total_out:,}")
    print(f" 예상 비용: ${cost:.4f}")
    print(f"{'='*55}\n")

    return all_cards


if __name__ == "__main__":
    run()
