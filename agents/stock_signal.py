"""
Agent 4 — Stock Signal
theme_report.json + 종목 DB → signals.json
테마를 ai_bottleneck_v2.html 종목에 매핑해 Buy/Hold/Sell 시그널 생성
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import types

# ── 경로
ROOT            = Path(__file__).parent.parent
DATA_DIR        = ROOT / "data"
REPORT_INPUT    = DATA_DIR / "theme_report.json"
SIGNALS_OUTPUT  = DATA_DIR / "signals.json"

# ── 설정
MODEL      = "gemini-2.5-flash"
MAX_TOKENS = 2000

# ── ai_bottleneck_v2.html 종목 DB (테마별 분류)
STOCK_DB = {
    "hyperscaler": {
        "label": "하이퍼스케일러",
        "theme_keys": ["gpu_compute", "software_ai"],
        "stocks": [
            {"k": "GOOGL", "n": "Alphabet",   "memo": "GCP·TPU·Gemini"},
            {"k": "MSFT",  "n": "Microsoft",  "memo": "Azure·OpenAI"},
            {"k": "AMZN",  "n": "Amazon",     "memo": "AWS·Trainium"},
            {"k": "META",  "n": "Meta",        "memo": "MTIA·Llama"},
            {"k": "ORCL",  "n": "Oracle",      "memo": "OCI GPU 클러스터"},
        ],
    },
    "memory": {
        "label": "메모리·HBM",
        "theme_keys": ["memory_hbm"],
        "stocks": [
            {"k": "005930.KS", "n": "삼성전자",    "memo": "서버D램·CXL·eSSD"},
            {"k": "000660.KS", "n": "SK하이닉스",  "memo": "HBM3E 선도"},
            {"k": "MU",        "n": "Micron",      "memo": "북미 유일 HBM"},
        ],
    },
    "network": {
        "label": "패키징·네트워킹",
        "theme_keys": ["networking"],
        "stocks": [
            {"k": "TSM",       "n": "TSMC",        "memo": "CoWoS 패키징 독점"},
            {"k": "AVGO",      "n": "Broadcom",    "memo": "AI 스위치칩·ASIC"},
            {"k": "ANET",      "n": "Arista",      "memo": "빅테크 이더넷 스위치"},
            {"k": "MRVL",      "n": "Marvell",     "memo": "광학 트랜시버·DSP"},
            {"k": "042700.KS", "n": "한미반도체",  "memo": "HBM TC Bonder 1위"},
        ],
    },
    "energy": {
        "label": "전력·냉각",
        "theme_keys": ["power_cooling"],
        "stocks": [
            {"k": "GEV",       "n": "GE Vernova",  "memo": "전력망 인프라 1위"},
            {"k": "VRT",       "n": "Vertiv",      "memo": "데이터센터 냉각 1위"},
            {"k": "CEG",       "n": "Constellation","memo": "미국 최대 원전"},
            {"k": "034020.KS", "n": "두산에너빌리티","memo": "SMR·원전 기자재"},
            {"k": "267260.KS", "n": "HD현대일렉트릭","memo": "북미 변압기 수혜"},
        ],
    },
    "mlcc": {
        "label": "MLCC",
        "theme_keys": ["gpu_compute", "memory_hbm"],
        "stocks": [
            {"k": "6981.T",    "n": "무라타",      "memo": "글로벌 MLCC 1위 45%"},
            {"k": "009150.KS", "n": "삼성전기",    "memo": "AI서버 MLCC 40% 점유"},
        ],
    },
    "physical_ai": {
        "label": "피지컬 AI",
        "theme_keys": ["software_ai"],
        "stocks": [
            {"k": "TSLA",      "n": "Tesla",       "memo": "Optimus·FSD"},
            {"k": "005380.KS", "n": "현대자동차",  "memo": "Boston Dynamics"},
        ],
    },
}

SYSTEM_PROMPT = """You are a senior equity derivatives trading desk head specializing in AI and memory semiconductor stocks at a Korean asset management firm.

Given a market theme report, assign Buy/Hold/Sell signals to each stock.

Signal criteria:
- BUY:  theme directly benefits this stock, conviction high, timing favorable
- WATCH: theme is positive but entry timing unclear or secondary beneficiary
- HOLD: neutral theme impact, maintain current position
- SELL: theme is negative for this stock, reduce exposure

Be decisive. Consider Korean market stocks (KS/KQ suffix) separately — Korean stocks have higher beta to global AI themes.
Return ONLY valid JSON, no markdown."""


# ────────────────────────────────────────────
#  프롬프트 빌더
# ────────────────────────────────────────────

def build_prompt(report: dict) -> str:
    # 종목 리스트 구성
    stock_list = []
    for group_key, group in STOCK_DB.items():
        for s in group["stocks"]:
            stock_list.append({
                "ticker":    s["k"],
                "name":      s["n"],
                "memo":      s["memo"],
                "group":     group["label"],
                "theme_keys": group["theme_keys"],
            })

    stocks_json = json.dumps(stock_list, ensure_ascii=False, indent=2)
    report_json = json.dumps({
        k: v for k, v in report.items()
        if k not in ["generated_at", "cards_analyzed", "input_tokens", "output_tokens"]
    }, ensure_ascii=False, indent=2)

    return f"""Market Theme Report:
{report_json}

Stock Universe:
{stocks_json}

For each stock, return a signal. Return ONLY this JSON:
{{
  "signals": [
    {{
      "ticker": "000660.KS",
      "name": "SK하이닉스",
      "group": "메모리·HBM",
      "signal": "BUY or WATCH or HOLD or SELL",
      "conviction": "HIGH or MEDIUM or LOW",
      "relevance_score": 0.0 to 1.0,
      "rationale": "1-2 sentence reason referencing specific CEO signal",
      "key_catalyst": "specific CEO name + what they said",
      "risk": "main downside risk for this stock",
      "time_horizon": "short(1-4w) or medium(1-3m) or long(3m+)"
    }}
  ]
}}

Include ALL {len(stock_list)} stocks in the signals array."""


# ────────────────────────────────────────────
#  Claude API 호출
# ────────────────────────────────────────────

def call_gemini(client: genai.Client, report: dict) -> tuple:
    prompt = build_prompt(report)
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

        result = json.loads(raw)
        return result.get("signals", []), response.usage_metadata

    except json.JSONDecodeError as e:
        print(f"  [JSON 파싱 실패] {e}")
        print(f"  Raw: {raw[:300]}")
        return None, None
    except Exception as e:
        print(f"  [API 오류] {e}")
        return None, None


# ────────────────────────────────────────────
#  메인
# ────────────────────────────────────────────

def run(report: dict | None = None) -> list:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*55}")
    print(f" [Stock Signal] 시작: {now_str}")
    print(f"{'='*55}")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    client = genai.Client(api_key=api_key)

    # 테마 리포트 로드
    if report is None:
        if not REPORT_INPUT.exists():
            print(" theme_report.json 없음 — 종료")
            return []
        report = json.loads(REPORT_INPUT.read_text(encoding="utf-8"))
        print(f" theme_report.json 로드 완료")

    print(f" Market Stance: {report.get('market_stance')} | Bottleneck: {report.get('primary_bottleneck')}")
    print(f"\n Gemini {MODEL} 시그널 생성 중...")

    signals, usage = call_gemini(client, report)

    if not signals:
        print(" [실패] 시그널 생성 불가")
        return []

    # 시그널 요약 출력
    from collections import Counter
    counts = Counter(s["signal"] for s in signals)
    print(f"\n  결과: BUY {counts.get('BUY',0)} / WATCH {counts.get('WATCH',0)} / HOLD {counts.get('HOLD',0)} / SELL {counts.get('SELL',0)}")
    print(f"\n  {'Ticker':<14} {'Signal':<7} {'Conv':<7} {'Rationale'}")
    print(f"  {'─'*70}")
    for s in sorted(signals, key=lambda x: ["BUY","WATCH","HOLD","SELL"].index(x["signal"])):
        print(f"  {s['ticker']:<14} {s['signal']:<7} {s['conviction']:<7} {s.get('rationale','')[:50]}")

    # 최종 output 구성
    output = {
        "last_updated":   datetime.now(timezone.utc).isoformat(),
        "market_stance":  report.get("market_stance"),
        "primary_bottleneck": report.get("primary_bottleneck"),
        "capex_momentum": report.get("capex_momentum"),
        "analyst_note_ko": report.get("analyst_note_ko"),
        "theme_tags":     report.get("theme_tags", []),
        "sector_outlook": report.get("sector_outlook", {}),
        "signals":        signals,
        "input_tokens":   (usage.prompt_token_count if usage else 0) or 0,
        "output_tokens":  (usage.candidates_token_count if usage else 0) or 0,
    }

    SIGNALS_OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cost = output["input_tokens"] * 0.075 / 1_000_000 + output["output_tokens"] * 0.30 / 1_000_000
    print(f"\n  토큰: input {output['input_tokens']:,} / output {output['output_tokens']:,}")
    print(f"  비용: ${cost:.4f}")
    print(f"\n{'='*55}\n")

    return signals


if __name__ == "__main__":
    run()
