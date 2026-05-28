#!/usr/bin/env python3
"""
아이 PF 모닝 알람 봇
매일 오전 7시 (KST) GitHub Actions에서 자동 실행
전일 종가 기준 분석 -> Telegram 전송
"""

import os, requests
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd

# ═══════════════════════════════════════
#  설정
# ═══════════════════════════════════════
PORTFOLIO = [
    {"t":"NVDA",      "s":39,  "n":"엔비디아",       "krw":False},
    {"t":"GOOGL",     "s":30,  "n":"알파벳 A",       "krw":False},
    {"t":"IONQ",      "s":55,  "n":"아이온큐",       "krw":False},
    {"t":"AVGO",      "s":11,  "n":"브로드컴",       "krw":False},
    {"t":"LLY",       "s":3,   "n":"일라이 릴리",    "krw":False},
    {"t":"AMZN",      "s":9,   "n":"아마존",         "krw":False},
    {"t":"BRK-B",     "s":9,   "n":"버크셔 B",       "krw":False},
    {"t":"PLTR",      "s":10,  "n":"팔란티어",       "krw":False},
    {"t":"CPNG",      "s":100, "n":"쿠팡",           "krw":False},
    {"t":"KBWB",      "s":18,  "n":"KBW Bank ETF",  "krw":False},
    {"t":"AOR",       "s":72,  "n":"Core Growth",   "krw":False},
    {"t":"BITO",      "s":44,  "n":"BTC ETF",       "krw":False},
    {"t":"INTC",      "s":15,  "n":"인텔",           "krw":False},
    {"t":"229200.KS", "s":227, "n":"KODEX 코스닥150","krw":True},
    {"t":"069500.KS", "s":243, "n":"KODEX 200",     "krw":True},
    {"t":"195920.KS", "s":152, "n":"TIGER 일본TOPIX","krw":True},
]

SURGE_UP   =  5.0   # +5% 이상 급등
SURGE_DOWN = -5.0   # -5% 이하 급락
BOT_TOKEN  = os.environ.get("BOT_TOKEN","")
CHAT_ID    = os.environ.get("CHAT_ID","")

# ═══════════════════════════════════════
#  기술 지표
# ═══════════════════════════════════════
def rsi(cl, period=14):
    d = cl.diff().dropna()
    g = d.clip(lower=0).rolling(period).mean().iloc[-1]
    l = (-d.clip(upper=0)).rolling(period).mean().iloc[-1]
    return round(100 if l==0 else 100-100/(1+g/l), 1)

def cloud_pos(price, hi, lo):
    n = len(hi)
    if n < 52: return "?"
    tn = (hi.rolling(9).max()+lo.rolling(9).min())/2
    kj = (hi.rolling(26).max()+lo.rolling(26).min())/2
    sa = ((tn+kj)/2).iloc[-27] if n>26 else float("nan")
    sb_h = hi.rolling(52).max().iloc[-27] if n>27 else float("nan")
    sb_l = lo.rolling(52).min().iloc[-27] if n>27 else float("nan")
    sb = (sb_h+sb_l)/2
    if pd.isna(sa) or pd.isna(sb): return "?"
    top,bot = max(sa,sb),min(sa,sb)
    return "above" if price>top else "below" if price<bot else "inside"

def detect_cross(cl, fw, sw, lb=10):
    fast = cl.rolling(fw).mean()
    slow = cl.rolling(sw).mean()
    for i in range(-lb,-1):
        pf,ps = fast.iloc[i],slow.iloc[i]
        cf,cs = fast.iloc[i+1],slow.iloc[i+1]
        if pd.isna(pf) or pd.isna(ps): continue
        if pf<ps and cf>cs: return "golden"
        if pf>ps and cf<cs: return "death"
    return None

# ═══════════════════════════════════════
#  종목 분석
# ═══════════════════════════════════════
def analyze(p):
    try:
        h  = yf.Ticker(p["t"]).history(period="2y", auto_adjust=True)
        if h.empty or len(h)<50: return None
        cl,hi,lo = h["Close"],h["High"],h["Low"]
        price  = round(float(cl.iloc[-1]),4)
        prev   = round(float(cl.iloc[-2]),4)
        chg    = round((price-prev)/prev*100,2)
        ma50   = round(float(cl.rolling(50).mean().iloc[-1]),2)
        ma100  = round(float(cl.rolling(100).mean().iloc[-1]),2)
        ma250  = round(float(cl.rolling(250).mean().iloc[-1]),2) if len(cl)>=250 else None
        vs50   = round((price-ma50)/ma50*100,1)
        cp     = cloud_pos(price,hi,lo)
        tn_v   = float((hi.rolling(9).max()+lo.rolling(9).min()).iloc[-1]/2)
        kj_v   = float((hi.rolling(26).max()+lo.rolling(26).min()).iloc[-1]/2)
        tk_sig = "bull" if tn_v>kj_v else "bear"
        rsi_v  = rsi(cl)
        h52    = float(hi.max()); l52=float(lo.min())
        rp     = round((price-l52)/(h52-l52)*100,1) if h52>l52 else 50
        c5100  = detect_cross(cl,50,100)
        c5250  = detect_cross(cl,50,250)
        # 수익률: 직전 금요일 / 전월 말일 기준
        last_date = cl.index[-1].date()
        import datetime as _dt
        # 직전 금요일
        dow = last_date.weekday()  # 0=월...4=금,5=토,6=일
        days_to_fri = (dow - 4) % 7 or 7  # 오늘이 금요일이면 7일 전
        last_fri = last_date - _dt.timedelta(days=int(days_to_fri))
        # 전월 말일
        first_of_month = last_date.replace(day=1)
        last_month_end = first_of_month - _dt.timedelta(days=1)

        def price_at(target_date):
            sub = cl[cl.index.date <= target_date]
            return float(sub.iloc[-1]) if not sub.empty else None
        def ret_at(target_date):
            p = price_at(target_date)
            return round((price-p)/p*100,1) if p and p>0 else None

        wk = ret_at(last_fri)        # 직전 금요일 대비
        mo = ret_at(last_month_end)  # 전월 말일 대비
        ytd=None
        try:
            ref=cl[cl.index.year==cl.index[-1].year-1]
            ytd=round((price-float(ref.iloc[-1]))/float(ref.iloc[-1])*100,1) if not ref.empty else None
        except: pass
        return {"t":p["t"],"n":p["n"],"s":p["s"],"krw":p["krw"],
                "price":price,"chg":chg,"ma50":ma50,"ma100":ma100,"ma250":ma250,
                "vs50":vs50,"cp":cp,"tk":tk_sig,"rsi":rsi_v,"rp52":rp,
                "c5100":c5100,"c5250":c5250,"wk":wk,"mo":mo,"ytd":ytd}
    except Exception as e:
        print(f"  {p['t']} 오류: {e}")
        return None

def get_fx():
    """현재 환율 + 과거 환율 반환 (환율효과 포함 손익 계산용)"""
    try:
        h = yf.Ticker("KRW=X").history(period="3mo", auto_adjust=True)
        if h.empty or len(h)<2: return 1520.0, 1520.0, 1520.0, 1520.0
        cl = h["Close"].dropna()
        cur  = round(float(cl.iloc[-1]), 2)
        d1   = round(float(cl.iloc[-2]),  2) if len(cl)>=2  else cur
        wk   = round(float(cl.iloc[-6]),  2) if len(cl)>=6  else cur
        mo   = round(float(cl.iloc[-23]), 2) if len(cl)>=23 else cur
        return cur, d1, wk, mo
    except:
        return 1520.0, 1520.0, 1520.0, 1520.0

# ═══════════════════════════════════════
#  메시지 포맷
# ═══════════════════════════════════════
def fp(v, sign=True):
    if v is None: return "—"
    return f"{'+'if sign and v>=0 else ''}{v:.1f}%"

CLOUD_E = {"above":"☁️↑","inside":"☁️≈","below":"☁️↓"}

def calc_pnl(results, fx, fx_d1=None, fx_wk=None, fx_mo=None):
    """전일/주간/월간 원화 손익 — 환율 변동 효과 포함"""
    fx_d1 = fx_d1 or fx
    fx_wk = fx_wk or fx
    fx_mo = fx_mo or fx
    cur = yd = wk = mo = 0.0
    for r in results:
        if not r: continue
        tk = r.get('t') or r.get('ticker')
        p_obj = next((p for p in PORTFOLIO if p['t']==tk), None)
        if not p_obj: continue
        shares = p_obj['s']
        krw    = p_obj['krw']
        price  = r.get('price'); 
        if not price: continue
        # 현재 원화가치
        cur += shares * price * (1.0 if krw else fx)
        # 과거 USD 가격 = 현재가 / (1 + 수익률%)
        # 과거 원화가치 = 과거USD가격 × 과거환율
        p_yd = price/(1+r['chg']/100)   if r.get('chg') is not None else price
        p_wk = price/(1+r['wk']/100)    if r.get('wk')  is not None else price
        p_mo = price/(1+r['mo']/100)    if r.get('mo')  is not None else price
        yd += shares * p_yd * (1.0 if krw else fx_d1)
        wk += shares * p_wk * (1.0 if krw else fx_wk)
        mo += shares * p_mo * (1.0 if krw else fx_mo)
    return {
        'cur':   round(cur),
        'd1':    round(cur - yd),
        'd1pct': round((cur-yd)/yd*100, 2) if yd else None,
        'wk':    round(cur - wk),
        'wkpct': round((cur-wk)/wk*100, 2) if wk else None,
        'mo':    round(cur - mo),
        'mopct': round((cur-mo)/mo*100, 2) if mo else None,
    }

def pnl_str(v, pct):
    if v is None: return "—"
    s = "+" if v >= 0 else ""
    e = "🟢" if v >= 0 else "🔴"
    p = f" ({s}{pct}%)" if pct is not None else ""
    return f"{e} {s}₩{abs(v):,}{p}"

def build_msg(results, fx, date_str, fx_d1=None, fx_wk=None, fx_mo=None):
    now_kst = (datetime.utcnow()+timedelta(hours=9)).strftime("%Y-%m-%d %H:%M KST")
    pnl = calc_pnl(results, fx, fx_d1, fx_wk, fx_mo)
    lines   = [f"📊 *아이 PF 모닝 리포트*",
               f"_{date_str} 전일종가 기준_  |  환율 ₩{fx:,.0f}","",
               "💰 *포트폴리오 손익 (원화)*",
               f"  전일: {pnl_str(pnl['d1'], pnl['d1pct'])}",
               f"  주간: {pnl_str(pnl['wk'], pnl['wkpct'])}",
               f"  월간: {pnl_str(pnl['mo'], pnl['mopct'])}",
               f"  총평가액: ₩{pnl['cur']:,}",
               ""]

    # 급등락
    surges = [(r,r["chg"]) for r in results if r and r["chg"]>=SURGE_UP]
    drops  = [(r,r["chg"]) for r in results if r and r["chg"]<=SURGE_DOWN]
    if surges or drops:
        lines.append("🚨 *급등락 알람*")
        for r,chg in sorted(surges,key=lambda x:-x[1]):
            lines.append(f"  🔺 `{r['t']}` {r['n']}  *{fp(chg)}*")
        for r,chg in sorted(drops,key=lambda x:x[1]):
            lines.append(f"  🔻 `{r['t']}` {r['n']}  *{fp(chg)}*")
        lines.append("")

    # 기술 신호
    sigs=[]
    for r in results:
        if not r: continue
        if r["c5100"]=="golden": sigs.append(f"  🔆 `{r['t']}` 골든크로스 MA50/100")
        if r["c5100"]=="death":  sigs.append(f"  💀 `{r['t']}` 데드크로스 MA50/100")
        if r["c5250"]=="golden": sigs.append(f"  🔆 `{r['t']}` 골든크로스 MA50/250")
        if r["c5250"]=="death":  sigs.append(f"  💀 `{r['t']}` 데드크로스 MA50/250")
        if r["cp"]=="below" and r["tk"]=="bear": sigs.append(f"  ☁️↓ `{r['t']}` 구름 아래+약세")
        if r["rsi"] and r["rsi"]<30: sigs.append(f"  📉 `{r['t']}` RSI {r['rsi']} 과매도")
        if r["rsi"] and r["rsi"]>75: sigs.append(f"  📈 `{r['t']}` RSI {r['rsi']} 과매수")
        if r["rp52"]>=95: sigs.append(f"  ⚡ `{r['t']}` 52주 고점 근접 {r['rp52']:.0f}%")
    if sigs:
        lines.append("📡 *기술 신호*")
        lines.extend(sigs); lines.append("")

    # 신호 없을 때
    if not surges and not drops and not sigs:
        lines.append("✅ 특이 신호 없음\n")

    # 종목 현황
    valid = [r for r in results if r]
    valid.sort(key=lambda r: -(r["s"]*r["price"] if r["krw"] else r["s"]*r["price"]*fx))
    lines.append("📈 *종목 현황 (보유액 순)*")
    lines.append("`종목        일일    주간   MA50  구름`")
    for r in valid:
        e = "🟢" if r["chg"]>=0 else "🔴"
        ce= CLOUD_E.get(r["cp"],"❓")+("↑"if r["tk"]=="bull"else "↓")
        lines.append(
            f"{e}`{r['t']:<10}` {fp(r['chg'],True):>6} "
            f"{fp(r['wk'],True):>6} {fp(r['vs50'],True):>6}  {ce}"
        )
    lines.append("")

    # 월간/YTD
    lines.append("📊 *수익률 (1개월 / YTD)*")
    for r in valid:
        lines.append(f"`{r['t']:<10}` {fp(r['mo'],True):>7}  {fp(r['ytd'],True):>7}")

    lines.append("")
    lines.append(f"_생성: {now_kst}_")
    lines.append("_⚠️ 투자권유 아님. 참고 목적._")
    return "\n".join(lines)

# ═══════════════════════════════════════
#  Telegram 전송
# ═══════════════════════════════════════
def send(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("TOKEN/CHAT_ID 없음 → 콘솔 출력:\n"); print(text); return
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id":CHAT_ID,"text":text,"parse_mode":"Markdown",
              "disable_web_page_preview":True},
        timeout=15
    )
    print("✅ 전송 완료" if r.status_code==200 else f"❌ 오류 {r.status_code}: {r.text}")

# ═══════════════════════════════════════
#  메인
# ═══════════════════════════════════════
def main():
    now = datetime.utcnow()+timedelta(hours=9)
    print(f"[{now.strftime('%Y-%m-%d %H:%M KST')}] 모닝 알람 시작")
    fx, fx_d1, fx_wk, fx_mo = get_fx()
    print(f"환율: ₩{fx:,.1f}  (전일 ₩{fx_d1:,.1f} / 주간 ₩{fx_wk:,.1f} / 월간 ₩{fx_mo:,.1f})")
    results=[]
    for p in PORTFOLIO:
        print(f"  {p['t']}...", end=" ", flush=True)
        r=analyze(p)
        results.append(r)
        print(f"${r['price']:.2f} ({r['chg']:+.2f}%)" if r else "실패")
    msg = build_msg(results, fx, now.strftime("%Y년 %m월 %d일"), fx_d1, fx_wk, fx_mo)
    send(msg)

if __name__=="__main__":
    main()
