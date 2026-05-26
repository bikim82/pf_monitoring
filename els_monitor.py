#!/usr/bin/env python3
"""ELS 모니터링 텔레그램 봇 — 06:30 / 13:00 / 18:00 KST"""
import os,requests
from datetime import datetime,timedelta
import yfinance as yf
import pandas as pd

BOT_TOKEN   = os.environ.get("ELS_BOT_TOKEN","")
ELS_CHAT_ID = os.environ.get("CHAT_ID","")
FRED_KEY    = os.environ.get("FRED_API_KEY","")
TV_USER     = os.environ.get("TV_USERNAME","")
TV_PASS     = os.environ.get("TV_PASSWORD","")

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
  "EURUSD":"EURUSD=X","USDJPY":"JPY=X","USDCNH":"CNH=X","DXY":"DX-Y.NYB",
  "WTI":"CL=F","BRENT":"BZ=F","GOLD":"GC=F","BTC":"BTC-USD",
  "VIX":"^VIX","VIX3M":"^VIX3M","VIX6M":"^VIX6M","VIX1Y":"^VIX1Y",
  "VKOSPI":"^VKOSPI",
  "UST10Y":"^TNX","UST30Y":"^TYX",
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
    h=yf.Ticker(ticker).history(period="5d",auto_adjust=True)
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
          res[k]=(v,round(v-p,3))
      except: pass
  except: pass
  return res

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
      return v,round(v-p,3)
  except: pass
  return None,None

# ─── 포맷 헬퍼 ────────────────────────────
def fp(v,c,dec=2,is_rate=False):
  if v is None: return "—"
  vs=f"{v:.{dec}f}"
  if c is None: return vs
  if is_rate: cs=f"({c:+.3f}bp)"
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
  asia=[("KOSPI200","KS200"),("NKY225","NKY"),("HSCEI","HSCEI")]
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
    v,c=yf_d.get(k,(None,None))
    L.append(f"{ae(c)}`{lbl2:<10}` {fp(v,c)}")
  L.append("")

  # 금리
  L.append("📉 *금리*")
  rate_rows=[
    ("UST", [("2Y","UST2Y"),("10Y","UST10Y"),("30Y","UST30Y")]),
    ("KTB", [("3Y","KTB3Y"),("10Y","KTB10Y"),("30Y","KTB30Y")]),
    ("JGB", [("10Y","JGB10Y"),("30Y","JGB30Y")]),
    ("EUR", [("Bund","BUND10Y"),("Gilt","GILT10Y"),("OAT","OAT10Y")]),
  ]
  for grp,items in rate_rows:
    parts=[]
    for tenor,k in items:
      d=tv_d.get(k) or (None,None)
      v,c=d
      parts.append(f"{tenor}:{fp(v,c,3,True) if v else '—'}")
    L.append(f"`{grp:<5}` {' | '.join(parts)}")
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
