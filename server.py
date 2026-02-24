"""
StockLens 백엔드 API
-------------------
설치:
    pip install fastapi uvicorn yfinance

실행:
    python server.py
    → http://localhost:8000

엔드포인트:
    GET /search?q=005930.KS   (한국 주식 - KRX 코드 뒤에 .KS 또는 .KQ)
    GET /search?q=AAPL        (미국 주식)
    GET /search?q=삼성전자     (종목명 검색 - KRX 기준)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf

app = FastAPI(title="StockLens API")

# CORS: 브라우저에서 localhost API 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# 한국 주요 종목명 → 티커 매핑 (필요에 따라 확장)
KR_TICKER_MAP = {
    "삼성전자": "005930.KS",
    "sk하이닉스": "000660.KS",
    "하이닉스": "000660.KS",
    "lg에너지솔루션": "373220.KS",
    "삼성바이오로직스": "207940.KS",
    "현대차": "005380.KS",
    "현대자동차": "005380.KS",
    "기아": "000270.KS",
    "셀트리온": "068270.KS",
    "포스코": "005490.KS",
    "포스코홀딩스": "005490.KS",
    "네이버": "035420.KS",
    "naver": "035420.KS",
    "카카오": "035720.KS",
    "kakao": "035720.KS",
    "삼성sdi": "006400.KS",
    "lg화학": "051910.KS",
    "kb금융": "105560.KS",
    "신한지주": "055550.KS",
    "하나금융지주": "086790.KS",
    "카카오뱅크": "323410.KS",
    "두산에너빌리티": "034020.KS",
    "에코프로비엠": "247540.KQ",
    "에코프로": "086520.KQ",
    "카카오게임즈": "293490.KQ",
}

# 배당 빈도 코드 → 한국어
FREQ_MAP = {
    1: "연 1회",
    2: "반기 (연 2회)",
    4: "분기 (연 4회)",
    12: "월배당 (연 12회)",
}


def resolve_ticker(query: str) -> str:
    """종목명 또는 코드를 yfinance 티커로 변환"""
    q = query.strip()
    
    # 이미 .KS / .KQ 포함하면 그대로
    if q.upper().endswith(".KS") or q.upper().endswith(".KQ"):
        return q.upper()
    
    # 숫자 6자리 → 한국 KS로 간주
    if q.isdigit() and len(q) == 6:
        return q + ".KS"
    
    # 종목명 매핑
    lower = q.lower()
    if lower in KR_TICKER_MAP:
        return KR_TICKER_MAP[lower]
    
    # 나머지는 미국 주식 티커로 간주
    return q.upper()


def fmt_market(ticker: str) -> str:
    if ticker.endswith(".KS") or ticker.endswith(".KQ"):
        return "KR"
    return "US"


@app.get("/search")
def search_stock(q: str):
    if not q or len(q.strip()) < 1:
        raise HTTPException(status_code=400, detail="검색어를 입력하세요.")

    ticker_str = resolve_ticker(q)
    
    try:
        ticker = yf.Ticker(ticker_str)
        info = ticker.info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 조회 실패: {str(e)}")

    # 유효한 종목인지 확인
    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        raise HTTPException(
            status_code=404,
            detail=f"'{q}' 종목을 찾을 수 없습니다. 코드를 확인하거나 .KS/.KQ를 붙여보세요."
        )

    # 현재가
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    
    # 전일 종가 기준 등락률
    prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
    price_change_pct = None
    if price and prev_close and prev_close != 0:
        price_change_pct = (price - prev_close) / prev_close * 100

    # ROE
    roe = info.get("returnOnEquity")

    # 배당 빈도
    freq_code = info.get("dividendFrequency") or info.get("trailingAnnualDividendRate")
    freq_label = FREQ_MAP.get(info.get("dividendFrequency"), None)
    
    # 배당금 및 배당률
    div_rate = info.get("dividendRate") or info.get("trailingAnnualDividendRate")
    div_yield = info.get("dividendYield") or info.get("trailingAnnualDividendYield")

    # 시가총액
    market_cap = info.get("marketCap")

    return {
        "ticker": ticker_str,
        "name": info.get("longName") or info.get("shortName") or ticker_str,
        "market": fmt_market(ticker_str),
        "current_price": price,
        "price_change_pct": price_change_pct,
        "per": info.get("trailingPE") or info.get("forwardPE"),
        "pbr": info.get("priceToBook"),
        "roe": roe,
        "high_52w": info.get("fiftyTwoWeekHigh"),
        "low_52w": info.get("fiftyTwoWeekLow"),
        "market_cap": market_cap,
        "dividend_yield": div_yield,
        "dividend_rate": div_rate,
        "dividend_frequency": freq_label,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
