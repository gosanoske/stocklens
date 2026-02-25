"""
StockLens 백엔드 API - 한국투자증권 KIS API 버전
-------------------
설치:
    pip install fastapi uvicorn requests

실행:
    python server.py
"""

import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="StockLens API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

KIS_APP_KEY = os.environ.get("KIS_APP_KEY")
KIS_APP_SECRET = os.environ.get("KIS_APP_SECRET")
KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"

# 액세스 토큰 캐시
_token_cache = {"access_token": None}


def get_access_token():
    """KIS API 액세스 토큰 발급"""
    if _token_cache["access_token"]:
        return _token_cache["access_token"]

    url = f"{KIS_BASE_URL}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
    }
    res = requests.post(url, json=body)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail="KIS 토큰 발급 실패")
    token = res.json().get("access_token")
    _token_cache["access_token"] = token
    return token


def kis_headers(tr_id: str):
    token = get_access_token()
    return {
        "authorization": f"Bearer {token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": tr_id,
        "Content-Type": "application/json; charset=utf-8",
    }


def is_korean(ticker: str) -> bool:
    """한국 주식 여부 판단"""
    return ticker.isdigit() or (len(ticker) == 6 and ticker[:6].isdigit())


def normalize_ticker(q: str) -> str:
    """티커 정규화"""
    q = q.strip()
    # .KS / .KQ 제거
    if q.upper().endswith(".KS") or q.upper().endswith(".KQ"):
        return q[:6]
    return q.upper()


def get_kr_stock(ticker: str) -> dict:
    """한국 주식 현재가 조회"""
    url = f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
    }
    res = requests.get(url, headers=kis_headers("FHKST01010100"), params=params)
    if res.status_code != 200:
        raise HTTPException(status_code=404, detail=f"종목을 찾을 수 없습니다: {ticker}")

    data = res.json()
    if data.get("rt_cd") != "0":
        raise HTTPException(status_code=404, detail=data.get("msg1", "조회 실패"))

    o = data["output"]
    price = float(o.get("stck_prpr", 0))
    prev_close = float(o.get("stck_sdpr", 0))
    change_pct = ((price - prev_close) / prev_close * 100) if prev_close else None

    return {
        "ticker": ticker,
        "name": o.get("hts_kor_isnm", ticker),
        "market": "KR",
        "current_price": price,
        "price_change_pct": change_pct,
        "per": float(o.get("per", 0)) or None,
        "pbr": float(o.get("pbr", 0)) or None,
        "roe": None,  # 별도 API 필요
        "high_52w": float(o.get("d250_hgpr", 0)) or None,
        "low_52w": float(o.get("d250_lwpr", 0)) or None,
        "market_cap": int(o.get("hts_avls", 0)) * 100000000 or None,
        "dividend_yield": None,
        "dividend_rate": None,
        "dividend_frequency": None,
    }


def get_us_stock(ticker: str) -> dict:
    """미국 주식 현재가 조회"""
    url = f"{KIS_BASE_URL}/uapi/overseas-price/v1/quotations/price"
    params = {
        "AUTH": "",
        "EXCD": "NAS" if ticker in ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GOOGL", "META"] else "NYS",
        "SYMB": ticker,
    }
    res = requests.get(url, headers=kis_headers("HHDFS00000300"), params=params)
    if res.status_code != 200:
        raise HTTPException(status_code=404, detail=f"종목을 찾을 수 없습니다: {ticker}")

    data = res.json()
    if data.get("rt_cd") != "0":
        raise HTTPException(status_code=404, detail=data.get("msg1", "조회 실패"))

    o = data["output"]
    price = float(o.get("last", 0))
    prev_close = float(o.get("base", 0))
    change_pct = ((price - prev_close) / prev_close * 100) if prev_close else None

    return {
        "ticker": ticker,
        "name": o.get("rsym", ticker),
        "market": "US",
        "current_price": price,
        "price_change_pct": change_pct,
        "per": float(o.get("perx", 0)) or None,
        "pbr": float(o.get("pbrx", 0)) or None,
        "roe": None,
        "high_52w": float(o.get("h52p", 0)) or None,
        "low_52w": float(o.get("l52p", 0)) or None,
        "market_cap": None,
        "dividend_yield": float(o.get("dyld", 0)) / 100 or None,
        "dividend_rate": None,
        "dividend_frequency": None,
    }


@app.get("/search")
def search_stock(q: str):
    if not q or len(q.strip()) < 1:
        raise HTTPException(status_code=400, detail="검색어를 입력하세요.")

    ticker = normalize_ticker(q)

    try:
        if is_korean(ticker):
            return get_kr_stock(ticker)
        else:
            return get_us_stock(ticker)
    except HTTPException:
        raise
    except Exception as e:
        # 토큰 만료 시 재발급
        _token_cache["access_token"] = None
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)