"""
Agent 1 — YouTube CEO Interview Scraper
API key 없이 youtube-search-python + youtube-transcript-api 사용
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from youtubesearchpython import VideosSearch
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

# ── 경로
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

RAW_OUTPUT   = DATA_DIR / "raw_content.json"
SEEN_IDS_FILE = DATA_DIR / "seen_ids.json"

# ── 검색 대상 CEO
CEO_QUERIES = [
    {
        "person":  "Jensen Huang",
        "company": "NVIDIA",
        "queries": ['"Jensen Huang" interview', '"Jensen Huang" AI GPU HBM'],
    },
    {
        "person":  "Satya Nadella",
        "company": "Microsoft",
        "queries": ['"Satya Nadella" AI', '"Satya Nadella" Azure interview'],
    },
    {
        "person":  "Sanjay Mehrotra",
        "company": "Micron",
        "queries": ['"Sanjay Mehrotra"', '"Micron CEO" memory HBM'],
    },
    {
        "person":  "Safra Catz",
        "company": "Oracle",
        "queries": ['"Safra Catz"', '"Oracle CEO" cloud AI infrastructure'],
    },
    {
        "person":  "Sergey Brin",
        "company": "Google",
        "queries": ['"Sergey Brin" AI', '"Sergey Brin" interview 2025 OR 2026'],
    },
    {
        "person":  "Mark Zuckerberg",
        "company": "Meta",
        "queries": ['"Zuckerberg" AI infrastructure', '"Mark Zuckerberg" AI interview'],
    },
    {
        "person":  "Elon Musk",
        "company": "xAI/Tesla",
        "queries": ['"Elon Musk" xAI interview', '"Elon Musk" AI compute'],
    },
]

RESULTS_PER_QUERY = 5   # 쿼리당 최대 검색 결과
REQUEST_DELAY     = 1.5  # 검색 요청 간격 (초) — YouTube 차단 방지


# ────────────────────────────────────────────
#  유틸
# ────────────────────────────────────────────

def load_seen_ids() -> set:
    if SEEN_IDS_FILE.exists():
        return set(json.loads(SEEN_IDS_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen_ids(seen: set):
    SEEN_IDS_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_recent(published_time_str: str) -> bool:
    """
    youtubesearchpython 반환 상대시간으로 48시간 이내 여부 판단.
    예: '3 hours ago', '1 day ago', '2 days ago', 'Just now'
    """
    if not published_time_str:
        return False
    s = published_time_str.lower()
    if any(x in s for x in ["second", "minute", "hour", "just now"]):
        return True
    if "day" in s:
        m = re.search(r"(\d+)\s+day", s)
        return bool(m and int(m.group(1)) <= 2)
    return False


def fetch_transcript(video_id: str) -> tuple:
    """
    (text, language_code) 반환.
    자막 없으면 (None, 'no_transcript').
    영어 수동 자막 → 영어 자동 자막 → 기타 언어 순 우선.
    youtube-transcript-api v1.x 방식 사용.
    """
    api = YouTubeTranscriptApi()
    try:
        # 사용 가능한 자막 목록 조회
        tlist = api.list(video_id)

        for method in [
            lambda: tlist.find_manually_created_transcript(["en"]),
            lambda: tlist.find_generated_transcript(["en"]),
            lambda: next(iter(tlist)),
        ]:
            try:
                t = method()
                entries = api.fetch(video_id, languages=[t.language_code])
                text = " ".join(e.text for e in entries).strip()
                return text, t.language_code
            except Exception:
                continue

        return None, "no_transcript"
    except (TranscriptsDisabled, NoTranscriptFound):
        return None, "no_transcript"
    except Exception as e:
        return None, f"error:{e}"


# ────────────────────────────────────────────
#  CEO별 검색 + 자막 수집
# ────────────────────────────────────────────

def safe_search(query: str, limit: int) -> list:
    """VideosSearch 실행, 파싱 실패한 개별 결과는 skip"""
    try:
        raw = VideosSearch(query, limit=limit).result()
        results = raw.get("result") or []
        # 필수 필드 없는 결과 제거
        return [v for v in results if v.get("id") and v.get("title")]
    except Exception as e:
        print(f"    [검색 오류] {e}")
        return []


def search_and_collect(ceo: dict, seen_ids: set) -> list:
    collected = []

    for query in ceo["queries"]:
        results = safe_search(query, RESULTS_PER_QUERY)
        if not results:
            time.sleep(REQUEST_DELAY)
            continue

        for video in results:
            vid_id = video.get("id", "")
            if not vid_id or vid_id in seen_ids:
                continue

            published_time = video.get("publishedTime", "")
            if not is_recent(published_time):
                continue

            title = video.get("title", "")[:80]
            print(f"    [신규] {title}  ({published_time})")

            transcript, lang = fetch_transcript(vid_id)

            # description snippet 병합
            desc_parts = video.get("descriptionSnippet") or []
            description = " ".join(p.get("text", "") for p in desc_parts)

            collected.append({
                "id":              vid_id,
                "source":          "youtube",
                "person":          ceo["person"],
                "company":         ceo["company"],
                "url":             f"https://www.youtube.com/watch?v={vid_id}",
                "title":           video.get("title", ""),
                "channel":         (video.get("channel") or {}).get("name", ""),
                "published_time":  published_time,
                "duration":        video.get("duration", ""),
                "view_count":      (video.get("viewCount") or {}).get("text", ""),
                "scraped_at":      datetime.now(timezone.utc).isoformat(),
                "has_transcript":  transcript is not None,
                "transcript_lang": lang,
                "transcript":      transcript,
                "description":     description,
            })

            seen_ids.add(vid_id)
            time.sleep(REQUEST_DELAY)

        time.sleep(REQUEST_DELAY)

    return collected


# ────────────────────────────────────────────
#  메인
# ────────────────────────────────────────────

def run() -> list:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*55}")
    print(f" [Scraper] 시작: {now_str}")
    print(f"{'='*55}")

    seen_ids     = load_seen_ids()
    all_new      = []

    for ceo in CEO_QUERIES:
        print(f"\n▶ {ceo['person']} ({ceo['company']})")
        new_items = search_and_collect(ceo, seen_ids)
        all_new.extend(new_items)
        print(f"  → {len(new_items)}건 수집")

    # 기존 데이터에 신규 append (최근 500건 유지)
    existing_items = []
    if RAW_OUTPUT.exists():
        try:
            existing_items = json.loads(RAW_OUTPUT.read_text(encoding="utf-8")).get("items", [])
        except Exception:
            pass

    combined = (existing_items + all_new)[-500:]

    output = {
        "last_updated":         datetime.now(timezone.utc).isoformat(),
        "total_items":          len(combined),
        "new_items_this_run":   len(all_new),
        "items":                combined,
    }

    RAW_OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    save_seen_ids(seen_ids)

    print(f"\n{'='*55}")
    print(f" [완료] 신규 {len(all_new)}건  →  {RAW_OUTPUT.name}")
    print(f"{'='*55}\n")

    return all_new


if __name__ == "__main__":
    run()
