"""
Pipeline — 오케스트레이터
Agent 1 → 2 → 3 → 4 순차 실행 후 signals.json을 GitHub에 push
하루 2회 (/schedule 또는 cron)으로 실행
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── GitHub Actions 환경 감지
IN_CI = bool(os.environ.get("GITHUB_ACTIONS"))

# ── 로컬 실행 시 git push 대상 경로
GITHUB_REPO = Path(r"C:\Users\xzero\Downloads\pf_monitoring")

# ── 에이전트 import
sys.path.insert(0, str(ROOT))
from agents.scraper        import run as run_scraper
from agents.summarizer     import run as run_summarizer
from agents.theme_analyzer import run as run_theme
from agents.stock_signal   import run as run_signal


# ────────────────────────────────────────────
#  GitHub push
# ────────────────────────────────────────────

def git_push():
    if IN_CI:
        # GitHub Actions 환경: 워크플로우가 git push 처리
        print("[Git] GitHub Actions 환경 — git push는 워크플로우가 처리")
        return

    src = ROOT / "data" / "signals.json"
    if not src.exists():
        print("[Git] signals.json 없음 — push 스킵")
        return

    if not GITHUB_REPO.exists():
        print(f"[Git] 레포 경로 없음: {GITHUB_REPO}")
        print("      git clone https://github.com/bikim82/pf_monitoring 먼저 실행")
        return

    import shutil
    dest_dir = GITHUB_REPO / "data"
    dest_dir.mkdir(exist_ok=True)
    shutil.copy2(src, dest_dir / "signals.json")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    cmds = [
        ["git", "add", "data/signals.json"],
        ["git", "commit", "-m", f"signals: {timestamp} auto-update"],
        ["git", "push"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, cwd=GITHUB_REPO, capture_output=True, text=True)
        if result.returncode != 0:
            if "nothing to commit" in result.stdout + result.stderr:
                print("[Git] 변경사항 없음 (signals.json 동일)")
                return
            print(f"[Git] 경고: {' '.join(cmd)}")
            print(f"      {result.stderr.strip()}")
            return
    print(f"[Git] push 완료: {timestamp}")


# ────────────────────────────────────────────
#  메인
# ────────────────────────────────────────────

def main():
    start = datetime.now()
    print(f"\n{'█'*55}")
    print(f"  AI Bottleneck CEO Signal Pipeline")
    print(f"  시작: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    if not os.environ.get("GEMINI_API_KEY"):
        raise EnvironmentError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.\n  $env:GEMINI_API_KEY = 'AIza...'")
    print(f"{'█'*55}")

    try:
        # ── Agent 1: 스크래핑
        print(f"\n[1/4] Scraper 실행 중...")
        new_items = run_scraper()

        if not new_items:
            print("  → 신규 항목 없음. 기존 intel_cards.json 기반으로 분석 계속.\n")

        # ── Agent 2: 요약
        print(f"\n[2/4] Summarizer 실행 중...")
        all_cards = run_summarizer(new_items if new_items else None)

        # ── Agent 3: 테마 분석
        print(f"\n[3/4] Theme Analyzer 실행 중...")
        report = run_theme(all_cards if isinstance(all_cards, list) and all_cards else None)

        if not report:
            print("  → 테마 분석 실패. 파이프라인 중단.")
            return

        # ── Agent 4: 종목 시그널
        print(f"\n[4/4] Stock Signal 실행 중...")
        signals = run_signal(report)

        # ── GitHub push
        print(f"\n[Push] GitHub 업데이트 중...")
        git_push()

    except Exception as e:
        print(f"\n[ERROR] 파이프라인 중단: {e}")
        raise

    elapsed = (datetime.now() - start).seconds
    print(f"\n{'█'*55}")
    print(f"  파이프라인 완료  —  소요 {elapsed}초")
    print(f"  signals.json → GitHub push 완료")
    print(f"{'█'*55}\n")


if __name__ == "__main__":
    main()
