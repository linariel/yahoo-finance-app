# -*- coding: utf-8 -*-
"""
Created on Sat Apr  4 21:28:46 2026

@author: Ariel
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import yfinance as yf

app = FastAPI()

# ── Serve the frontend UI ──────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index():
    with open("index.html", encoding="utf-8") as f:
        return f.read()

# ── API: Get stock info ────────────────────────────────
@app.get("/stock/{ticker}")
def get_stock(ticker: str):
    try:
        stock = yf.Ticker(ticker.upper())
        info = stock.info

        return {
            "symbol":   info.get("symbol", ticker.upper()),
            "name":     info.get("longName", "N/A"),
            "price":    info.get("currentPrice") or info.get("regularMarketPrice", "N/A"),
            "currency": info.get("currency", "USD"),
            "market_cap": info.get("marketCap", "N/A"),
            "pe_ratio": info.get("trailingPE", "N/A"),
            "52w_high": info.get("fiftyTwoWeekHigh", "N/A"),
            "52w_low":  info.get("fiftyTwoWeekLow", "N/A"),
            "sector":   info.get("sector", "N/A"),
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Could not fetch data for '{ticker}': {str(e)}")

# ── API: Get historical price data ────────────────────
@app.get("/history/{ticker}")
def get_history(ticker: str, period: str = "1mo"):
    """
    period options: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y
    """
    try:
        stock = yf.Ticker(ticker.upper())
        hist = stock.history(period=period)
        
        if hist.empty:
            raise HTTPException(status_code=404, detail="No data found")

        return {
            "ticker": ticker.upper(),
            "period": period,
            "data": [
                {
                    "date":  str(index.date()),
                    "open":  round(row["Open"], 2),
                    "high":  round(row["High"], 2),
                    "low":   round(row["Low"], 2),
                    "close": round(row["Close"], 2),
                    "volume": int(row["Volume"]),
                }
                for index, row in hist.iterrows()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))