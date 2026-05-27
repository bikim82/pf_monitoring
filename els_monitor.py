#!/usr/bin/env python3
"""ELS 모니터링 텔레그램 봇 — 06:30 / 13:00 / 18:00 KST"""
import os,requests
from datetime import datetime,timedelta
import yfinance as yf
import pandas as pd

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ELS_CHAT_ID = os.environ.get("ELS_CHAT_ID", "")
FRED_KEY = os.environ.get("FRED_API_KEY", "")
TV_USER = os.environ.get("TV_USERNAME", "")
TV_PASS = os.environ.get("TV_PASSWORD", "")

UTC_H = datetime.utcnow().hour
if   UTC_H in [21,22]:  SES="morning"
elif UTC_H in [3,4,5]:  SES="midday"
elif UTC_H in [8,9,10]: SES="evening"
else:                    SES="morning"

# ─── 티커 정의 ─────────────────────────────
YF_MAP = {
  "KOSPI200":"^KS200","NKY225":"^N225","HSCEI":"^HSCE",
  "SX5E":"^STOXX50E","SPX":"^GSPC","MXWO":"URTH","MXEF":"EEM",
  "ES1":"ES=F","SX5E_fut":"^STOXX50E","NIY1":"NIY=F",
  "USDKRW":"KRW=X","JPYKRW":"JPYKRW=X","EURKRW":"EURKRW=X",
  "EURUSD":"EURUSD=X","USDJPY":"JPY=X","USDCNH":"CNH=X","USDCNH_ALT":"USDCNH=X","USDCNH_ALT2":"6N=F","DXY":"DX-Y.NYB",
  "WTI":"CL=F","BRENT":"BZ=F","GOLD":"GC=F","BTC":"BTC-USD",
  "VIX":"^VIX","VIX3M":"^VIX3M","VIX6M":"^VIX6M","VIX1Y":"^VIX1Y",
  "VKOSPI":"^VKOSPI",
  "UST10Y":"^TNX","UST30Y":"^TYX",
  # 한국주식
  "KR_005930":"005930.KS",
  "KR_000660":"000660.KS",
  "KR_005380":"005380.KS",
  "KR_066570":"066570.KS",
  "KR_051910":"051910.KS",
  "KR_005490":"005490.KS",
  "KR_329180":"329180.KS",
  "KR_016360":"016360.KS",
  # 글로벌주식
  "GL_NVDA":"NVDA",
  "GL_AAPL":"AAPL",
  "GL_TSLA":"TSLA",
  "GL_AMZN":"AMZN",
  "GL_TSM":"TSM",
  "GL_AMD":"AMD",
  "GL_MSFT":"MSFT",
  "GL_META":"META",
  "GL_GOOGL":"GOOGL",
  "GL_INTC":"INTC",
  "GL_AVGO":"AVGO",
  "GL_PLTR":"PLTR",
  "GL_MU":"MU",
  "GL_ORCL":"ORCL",
  "GL_ARM":"ARM",
  "GL_UNH":"UNH",
  "GL_JPM":"JPM",
  "GL_GS":"GS",
}
TV_MAP = {
  "UST2Y":("US02Y","TVC"),"UST10Y":("US10Y","TVC"),"UST30Y":("US30Y","TVC"),
  "KTB3Y":("KR03Y","TVC"),"KTB10Y":("KR10Y","TVC"),"KTB30Y":("KR30Y","TVC"),
  "JGB10Y":("JP10Y","TVC"),"JGB30Y":("JP30Y","TVC"),
  "BUND10Y":("DE10Y","TVC"),"GILT10Y":("GB10Y","TVC"),"OAT10Y":("FR10Y","TVC"),
  "V2X":("V2TX","EUREX"),
}
FRED_MAP = {
  "UST2Y":"DGS2","UST10Y":"DGS10","UST30Y":"DGS30",
  "KTB10Y":"IRLTLT01KRM156N","JGB10Y":"IRLTLT01JPM156N",
  "BUND10Y":"IRLTLT01DEM156N","GILT10Y":"IRLTLT01GBM156N","OAT10Y":"IRLTLT01FRM156N",
}

# ─── 데이터 수집 ───────────────────────────
def gyt(ticker):
  try:
    h=yf.Ticker(ticker).history(period="6mo",auto_adjust=True)
    if h.empty or len(h)<2: return None,None
    v=round(float(h["Close"].iloc[-1]),4)
    p=round(float(h["Close"].iloc[-2]),4)
    return v,round((v-p)/p*100,2) if p else (v,None)
  except: return None,None

def gtv():
  res={}
  try:
    from tvDatafeed import TvDatafeed,Interval
    tv=TvDatafeed(TV_USER,TV_PASS) if TV_USER and TV_PASS else TvDatafeed()
    for k,(sym,exch) in TV_MAP.items():
      try:
        df=tv.get_hist(sym,exch,interval=Interval.in_daily,n_bars=3)
        if df is not None and len(df)>=2:
          v=round(float(df["close"].iloc[-1]),3)
          p=round(float(df["close"].iloc[-2]),3)
          res[k]=(v,round((v-p)*100,1))
      except: pass
  except: pass
  return res

def analyze_stock(ticker):
    """종목 상세 분석: 가격, 수익률, MA50, 구름대"""
    try:
        h = yf.Ticker(ticker).history(period="18mo", auto_adjust=True)
        if h.empty or len(h)<50: return None
        cl,hi,lo = h["Close"].dropna(), h["High"], h["Low"]
        price = round(float(cl.iloc[-1]),4)
        prev  = round(float(cl.iloc[-2]),4)
        chg1d = round((price-prev)/prev*100,2) if prev else None
        # 주간/월간/YTD (days로 변수명 변경 — n 충돌 방지)
        def hr(days):
            sub=cl.iloc[-days:] if len(cl)>=days else cl
            return round((price-float(sub.iloc[0]))/float(sub.iloc[0])*100,1) if len(sub)>1 else None
        wk=hr(6); mo=hr(22)
        ytd=None
        try:
            ref=cl[cl.index.year==cl.index[-1].year-1]
            ytd=round((price-float(ref.iloc[-1]))/float(ref.iloc[-1])*100,1) if not ref.empty else None
        except: pass
        # MA50
        ma50=round(float(cl.rolling(50).mean().iloc[-1]),2)
        vs50=round((price-ma50)/ma50*100,1) if ma50 else None
        # 일목 구름대 (간략)
        n=len(cl); tn=kj=float('nan')
        hi_=hi.reindex(cl.index); lo_=lo.reindex(cl.index)
        if n>=26:
            tn=float((hi_.rolling(9).max()+lo_.rolling(9).min()).iloc[-1]/2)
            kj=float((hi_.rolling(26).max()+lo_.rolling(26).min()).iloc[-1]/2)
        sa=sb=float('nan')
        if n>=52:
            sa=float(((hi_.rolling(9).max()+lo_.rolling(9).min())/2).shift(26).iloc[-1])
            sb=float(((hi_.rolling(52).max()+lo_.rolling(52).min())/2).shift(26).iloc[-1])
        import math
        cloud='?' 
        if not (math.isnan(sa) or math.isnan(sb)):
            top,bot=max(sa,sb),min(sa,sb)
            cloud='☁↑' if price>top else '☁↓' if price<bot else '☁≈'
        tk='↑' if not (math.isnan(tn) or math.isnan(kj)) and tn>kj else '↓'
        return {'price':price,'chg1d':chg1d,'wk':wk,'mo':mo,'ytd':ytd,
                'vs50':vs50,'cloud':cloud,'tk':tk}
    except: return None

def gfred(sid):
  if not FRED_KEY: return None,None
  try:
    r=requests.get("https://api.stlouisfed.org/fred/series/observations",
      params={"series_id":sid,"api_key":FRED_KEY,"file_type":"json",
              "sort_order":"desc","limit":3},timeout=10)
    obs=[o for o in r.json().get("observations",[]) if o["value"]!="."]
    if len(obs)>=2:
      v=round(float(obs[0]["value"]),3)
      p=round(float(obs[1]["value"]),3)
      return v,round((v-p)*100,1)
  except: pass
  return None,None

# ─── 포맷 헬퍼 ────────────────────────────
def fp(v,c,dec=2,is_rate=False):
  if v is None: return "—"
  vs=f"{v:.{dec}f}"
  if c is None: return vs
  if is_rate: cs=f"({c:+.1f}bp)"
  else:        cs=f"({c:+.2f}%)"
  return f"{vs} {cs}"
def ae(c): return "🔺"if c and c>0 else"🔻"if c and c<0 else"  "

# ─── 메시지 빌드 ──────────────────────────
def build(yf_d,tv_d,ses):
  now=(datetime.utcnow()+timedelta(hours=9)).strftime("%Y-%m-%d %H:%M KST")
  lbl={"morning":"🌅 06:30 모닝","midday":"☀️ 13:00 낮","evening":"🌆 18:00 저녁"}[ses]
  L=[f"📊 *ELS 모니터링 — {lbl}*",f"_{now}_",""]

  # 주식지수
  L.append("📈 *주식 지수*")
  asia=[("KOSPI200","KOSPI200"),("NKY225","NKY225"),("HSCEI","HSCEI")]
  if ses=="morning":
    euus=[("SX5E","SX5E"),("SPX","SPX")]
  else:
    euus=[("SX5E","SX5E"),("SPX선물","ES1")]
  for lbl2,k in asia+euus+[("MXWO","MXWO"),("MXEF","MXEF")]:
    v,c=yf_d.get(k,(None,None))
    L.append(f"{ae(c)}`{lbl2:<12}` {fp(v,c)}")
  L.append("")

  # FX
  L.append("💱 *환율*")
  fx_list=[("USDKRW","USDKRW"),("JPYKRW","JPYKRW"),("EURKRW","EURKRW"),
           ("EURUSD","EURUSD"),("USDJPY","USDJPY"),("USDCNH","USDCNH"),("DXY","DXY")]
  for lbl2,k in fx_list:
    dat=yf_d.get(k) or yf_d.get(k+"_ALT") or yf_d.get(k+"_ALT2",(None,None))
    v,ch=(dat if dat else (None,None))
    L.append(f"{ae(ch)}`{lbl2:<10}` {fp(v,ch)}")
  L.append("")

  # 금리
  L.append("📉 *금리*")
  rate_rows=[
    ("🇺🇸UST", [("2Y","UST2Y"),("10Y","UST10Y"),("30Y","UST30Y")]),
    ("🇰🇷KTB", [("3Y","KTB3Y"),("10Y","KTB10Y"),("30Y","KTB30Y")]),
    ("🇯🇵JGB", [("10Y","JGB10Y"),("30Y","JGB30Y")]),
    ("🇩🇪Bund",[("10Y","BUND10Y")]),
    ("🇬🇧Gilt",[("10Y","GILT10Y")]),
    ("🇫🇷OAT", [("10Y","OAT10Y")]),
  ]
  for grp,items in rate_rows:
    parts=[]
    for tenor,k in items:
      dat=tv_d.get(k,(None,None))
      v,ch=(dat if dat else (None,None))
      if v:
        bp_s=f"({ch:+.1f}bp)" if ch is not None else ""
        parts.append(f"{tenor} `{v:.3f}%` {bp_s}")
      else:
        parts.append(f"{tenor} —")
    L.append(f"{grp}: {' / '.join(parts)}")
  L.append("")

  # 원자재
  L.append("🛢️ *원자재·변동성*")
  for lbl2,k in [("WTI","WTI"),("Brent","BRENT"),("Gold","GOLD"),("BTC","BTC")]:
    v,c=yf_d.get(k,(None,None))
    L.append(f"{ae(c)}`{lbl2:<8}` {fp(v,c)}")
  for lbl2,k in [("VIX","VIX"),("VIX3M","VIX3M"),("VIX6M","VIX6M"),("VIX1Y","VIX1Y"),
                  ("VKOSPI","VKOSPI"),("V2X","V2X")]:
    # VKOSPI → yfinance, V2X → tvDatafeed (없으면 생략)
    d=tv_d.get(k,(None,None)) if k=="V2X" else yf_d.get(k,(None,None))
    v,c=(d if d else (None,None))
    L.append(f"{ae(c)}`{lbl2:<8}` {fp(v,c)}")
  L.append("")
  # 주식 섹션 (아침에만)
  if ses=="morning":
    KR_LIST=[("005930.KS","삼성전자"),("000660.KS","SK하이닉스"),
             ("005380.KS","현대차"),("066570.KS","LG전자"),
             ("051910.KS","LG화학"),("005490.KS","포스코홀딩스"),
             ("329180.KS","HD현대중공업"),("016360.KS","삼성증권")]
    GL_LIST=[("NVDA","NVIDIA"),("AAPL","Apple"),("TSLA","Tesla"),("AMZN","Amazon"),
             ("TSM","TSMC"),("AMD","AMD"),("MSFT","Microsoft"),("META","Meta"),
             ("GOOGL","Alphabet"),("INTC","Intel"),("AVGO","Broadcom"),
             ("PLTR","Palantir"),("MU","Micron"),("JPM","JPMorgan"),("GS","Goldman")]

    L.append("🇰🇷 *한국 주요주*")
    L.append("`종목       전일    주간   MA50  구름  1개월  YTD`")
    for t,n in KR_LIST:
      r=analyze_full(t)
      if not r: continue
      pr=f"₩{int(r['price']):,}"
      d1s=f"{r['chg1d']:+.1f}%" if r['chg1d'] else "—"
      wks=f"{r['wk']:+.1f}%" if r['wk'] else "—"
      m50s=f"{r['vs50']:+.1f}%" if r['vs50'] else "—"
      mos=f"{r['mo']:+.1f}%" if r['mo'] else "—"
      ytds=f"{r['ytd']:+.1f}%" if r['ytd'] else "—"
      e="🟢" if r['chg1d'] and r['chg1d']>=0 else "🔴"
      L.append(f"{e}`{n:<8}` {d1s:>6} {wks:>6} {m50s:>6} {r['cloud']}{r['tk']} {mos:>6} {ytds:>6}")
    L.append("")

    L.append("🌐 *글로벌 주요주*")
    L.append("`종목       현재가   전일   주간   MA50  구름`")
    for t,n in GL_LIST:
      r=analyze_full(t)
      if not r: continue
      d1s=f"{r['chg1d']:+.1f}%" if r['chg1d'] else "—"
      wks=f"{r['wk']:+.1f}%" if r['wk'] else "—"
      m50s=f"{r['vs50']:+.1f}%" if r['vs50'] else "—"
      e="🟢" if r['chg1d'] and r['chg1d']>=0 else "🔴"
      L.append(f"{e}`{n:<8}` ${r['price']:.1f} {d1s:>6} {wks:>6} {m50s:>6} {r['cloud']}{r['tk']}")
    L.append("")

  L.append(f"_소스: yfinance · tvDatafeed · FRED_")
  L.append("_⚠️ 참고용, 투자권유 아님_")
  return "\n".join(L)

def send(text):
  if not BOT_TOKEN or not ELS_CHAT_ID:
    print("TOKEN/CHAT_ID 없음:\n"); print(text); return
  r=requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
    json={"chat_id":ELS_CHAT_ID,"text":text,"parse_mode":"Markdown",
          "disable_web_page_preview":True},timeout=15)
  print("✅ 전송 완료" if r.status_code==200 else f"❌ {r.status_code}: {r.text[:200]}")

def main():
  now=(datetime.utcnow()+timedelta(hours=9))
  print(f"[{now.strftime('%Y-%m-%d %H:%M KST')}] ELS 모니터링 — {SES}")
  print("[yfinance]")
  yf_d={}
  for k,t in YF_MAP.items():
    v,c=gyt(t)
    if v: yf_d[k]=(v,c); print(f"  {k}: {v}")
  print("[tvDatafeed]")
  tv_d=gtv()
  if FRED_KEY:
    print("[FRED 폴백]")
    for k,s in FRED_MAP.items():
      if k not in tv_d:
        v,c=gfred(s)
        if v: tv_d[k]=(v,c); print(f"  FRED {k}: {v}")
  send(build(yf_d,tv_d,SES))

if __name__=="__main__": main()
