"""
Agent 3 — Theme Analyzer
intel_cards.json → theme_report.json
복수 CEO 발언을 종합해 AI Bottleneck 위치 및 시장 방향 진단
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import types

# ── 경로
ROOT          = Path(__file__).parent.parent
DATA_DIR      = ROOT / "data"
CARDS_INPUT   = DATA_DIR / "intel_cards.json"
REPORT_OUTPUT = DATA_DIR / "theme_report.json"

# ── 설정
MODEL      = "gemini-2.5-flash"
MAX_TOKENS = 1200

SYSTEM_PROMPT = """You are a chief investment strategist specializing in AI infrastructure and semiconductor sector at a Korean asset management firm.

Your task: synthesize multiple CEO statements into a unified market intelligence report.

Key judgment framework:
- AI Bottleneck location: where is the current constraint in the AI stack?
  (Compute → Memory/HBM → Networking → Power/Cooling → Software efficiency)
- Market stance: are CEO signals collectively bullish, neutral, or bearish?
- Capex momentum: is hyperscaler spending accelerating, stable, or decelerating?
- Bottleneck shift: is the bottleneck moving from one layer to another?

Be decisive. Assign clear stances. Avoid vague hedging.
Return ONLY valid JSON, no markdown, no explanation."""


# ────────────────────────────────────────────
#  최근 카드 로드 (72시간 이내)
# ────────────────────────────────────────────

def load_recent_cards(hours: int = 168) -> list:  # 7일
    if not CARDS_INPUT.exists():
        return []
    data = json.loads(CARDS_INPUT.read_text(encoding="utf-8"))
    cards = data.get("cards", [])

    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    recent = [c for c in cards if c.get("analyzed_at", "") >= cutoff]

    if not recent:
        recent = cards[-10:]

    return recent


# ────────────────────────────────────────────
#  프롬프트 빌더
# ────────────────────────────────────────────

def build_prompt(cards: list) -> str:
    card_summaries = []
    for c in cards:
        summary = {
            "person":               c.get("person"),
            "company":              c.get("company"),
            "published_time":       c.get("published_time"),
            "sentiment":            c.get("sentiment"),
            "sentiment_score":      c.get("sentiment_score"),
            "capex_signal":         c.get("capex_signal"),
            "bottleneck_mentioned": c.get("bottleneck_mentioned", []),
            "demand_outlook":       c.get("demand_outlook"),
            "supply_concern":       c.get("supply_concern"),
            "new_product_signal":   c.get("new_product_signal"),
            "macro_risk":           c.get("macro_risk"),
            "urgency":              c.get("urgency"),
            "key_quotes":           c.get("key_quotes", [])[:2],
            "summary_ko":           c.get("summary_ko"),
        }
        card_summaries.append(summary)

    cards_json = json.dumps(card_summaries, ensure_ascii=False, indent=2)
    today = datetime.now().strftime("%Y-%m-%d")

    return f"""Today is {today}. Analyze these {len(cards)} CEO intelligence cards and produce a unified market theme report.

INTEL CARDS:
{cards_json}

Return ONLY this JSON structure:

{{
  "report_date": "{today}",
  "market_stance": "BULL or NEUTRAL or BEAR",
  "stance_confidence": 0.0 to 1.0,
  "stance_rationale": "2-3 sentence reasoning for the stance",

  "primary_bottleneck": "Memory/HBM or Compute/GPU or Networking or Power/Cooling or Software or None",
  "secondary_bottleneck": "same options or null",
  "bottleneck_rationale": "evidence from CEO statements",
  "bottleneck_shift": "description of any shift in bottleneck location, or null",

  "capex_momentum": "accelerating or stable or decelerating",
  "capex_evidence": ["quote or signal 1", "quote or signal 2"],

  "key_catalysts": [
    {{"person": "...", "signal": "...", "impact": "bullish or bearish"}}
  ],
  "risk_factors": ["risk 1", "risk 2"],

  "sector_outlook": {{
    "memory_hbm":    "bullish or neutral or bearish",
    "gpu_compute":   "bullish or neutral or bearish",
    "networking":    "bullish or neutral or bearish",
    "power_cooling": "bullish or neutral or bearish",
    "software_ai":   "bullish or neutral or bearish"
  }},

  "theme_tags": ["HBM", "capex_acceleration", "..."],

  "analyst_note_ko": "3-4줄 한국어 종합 코멘트 (trading desk용)"
}}"""


# ────────────────────────────────────────────
#  Gemini API 호출
# ────────────────────────────────────────────

def call_gemini(client: genai.Client, cards: list) -> dict | None:
    prompt = build_prompt(cards)
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=MAX_TOKENS,
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

        report = json.loads(raw)
        report["generated_at"]  = datetime.now(timezone.utc).isoformat()
        report["cards_analyzed"] = len(cards)
        report["input_tokens"]   = response.usage_metadata.prompt_token_count or 0
        report["output_tokens"]  = response.usage_metadata.candidates_token_count or 0
        return report

    except json.JSONDecodeError as e:
        print(f"  [JSON 파싱 실패] {e}")
        print(f"  Raw: {raw[:300]}")
        return None
    except Exception as e:
        print(f"  [API 오류] {e}")
        return None


# ────────────────────────────────────────────
#  메인
# ────────────────────────────────────────────

def run(cards: list | None = None) -> dict | None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*55}")
    print(f" [Theme Analyzer] 시작: {now_str}")
    print(f"{'='*55}")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    client = genai.Client(api_key=api_key)

    if cards is not None:
        target_cards = cards
        print(f" Agent 2에서 전달받은 카드: {len(target_cards)}장")
    else:
        target_cards = load_recent_cards(hours=168)
        print(f" intel_cards.json에서 로드: {len(target_cards)}장 (최근 7일)")

    if not target_cards:
        print(" 분석할 카드 없음 — 종료")
        return None

    persons = list({c.get("person") for c in target_cards})
    print(f" 포함 CEO: {', '.join(persons)}")

    print(f"\n Gemini {MODEL} 분석 중...")
    report = call_gemini(client, target_cards)

    if not report:
        print(" [실패] 리포트 생성 불가")
        return None

    REPORT_OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n {'─'*45}")
    print(f"  Market Stance : {report.get('market_stance')}  (confidence {report.get('stance_confidence', 0):.0%})")
    print(f"  Bottleneck    : {report.get('primary_bottleneck')}  →  {report.get('secondary_bottleneck')}")
    print(f"  Capex         : {report.get('capex_momentum')}")
    print(f"  Tags          : {', '.join(report.get('theme_tags', []))}")
    print(f"\n  Analyst Note:")
    print(f"  {report.get('analyst_note_ko', '')}")
    print(f" {'─'*45}")
    cost = report['input_tokens'] * 0.075 / 1_000_000 + report['output_tokens'] * 0.30 / 1_000_000
    print(f"\n  토큰: input {report['input_tokens']:,} / output {report['output_tokens']:,}")
    print(f"  비용: ${cost:.4f}")
    print(f"\n{'='*55}\n")

    return report


if __name__ == "__main__":
    run()
