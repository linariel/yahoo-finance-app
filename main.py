from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import yfinance as yf
import sqlite3
import os

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "stocks.db")

# ── Database setup ─────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker    TEXT NOT NULL UNIQUE,
            note      TEXT,
            added_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker     TEXT NOT NULL,
            quantity   REAL NOT NULL,
            buy_price  REAL NOT NULL,
            added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker       TEXT NOT NULL,
            target_price REAL NOT NULL,
            condition    TEXT NOT NULL CHECK(condition IN ('above', 'below')),
            triggered    INTEGER DEFAULT 0,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS stock_prices (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker   TEXT NOT NULL,
            date     TEXT NOT NULL,
            open     REAL,
            high     REAL,
            low      REAL,
            close    REAL,
            volume   INTEGER,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ticker, date)
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ── Pydantic models ────────────────────────────────────
class WatchlistItem(BaseModel):
    ticker: str
    note: Optional[str] = ""

class PortfolioItem(BaseModel):
    ticker: str
    quantity: float
    buy_price: float

class AlertItem(BaseModel):
    ticker: str
    target_price: float
    condition: str

class StockPriceItem(BaseModel):
    ticker: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int

# ── Serve frontend ─────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(BASE_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()

# ── Yahoo Finance ──────────────────────────────────────
@app.get("/stock/{ticker}")
def get_stock(ticker: str):
    try:
        stock = yf.Ticker(ticker.upper())
        info  = stock.info
        return {
            "symbol":     info.get("symbol", ticker.upper()),
            "name":       info.get("longName", "N/A"),
            "price":      info.get("currentPrice") or info.get("regularMarketPrice", "N/A"),
            "currency":   info.get("currency", "USD"),
            "market_cap": info.get("marketCap", "N/A"),
            "pe_ratio":   info.get("trailingPE", "N/A"),
            "52w_high":   info.get("fiftyTwoWeekHigh", "N/A"),
            "52w_low":    info.get("fiftyTwoWeekLow", "N/A"),
            "sector":     info.get("sector", "N/A"),
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/history/{ticker}")
def get_history(ticker: str, period: str = "1mo"):
    try:
        stock = yf.Ticker(ticker.upper())
        hist  = stock.history(period=period)
        if hist.empty:
            raise HTTPException(status_code=404, detail="No data found")
        return {
            "ticker": ticker.upper(),
            "period": period,
            "data": [
                {
                    "date":   str(idx.date()),
                    "open":   round(row["Open"], 2),
                    "high":   round(row["High"], 2),
                    "low":    round(row["Low"], 2),
                    "close":  round(row["Close"], 2),
                    "volume": int(row["Volume"]),
                }
                for idx, row in hist.iterrows()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ══════════════════════════════════════════════════════
#  WATCHLIST CRUD
# ══════════════════════════════════════════════════════
@app.get("/watchlist")
def get_watchlist():
    conn = get_db()
    rows = conn.execute("SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/watchlist")
def add_to_watchlist(item: WatchlistItem):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO watchlist (ticker, note) VALUES (?, ?)",
            (item.ticker.upper(), item.note)
        )
        conn.commit()
        conn.close()
        return {"message": f"{item.ticker.upper()} added to watchlist"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Ticker already in watchlist")

@app.put("/watchlist/{id}")
def update_watchlist(id: int, item: WatchlistItem):
    conn = get_db()
    conn.execute(
        "UPDATE watchlist SET ticker=?, note=? WHERE id=?",
        (item.ticker.upper(), item.note, id)
    )
    conn.commit()
    conn.close()
    return {"message": "Watchlist item updated"}

@app.delete("/watchlist/{id}")
def delete_watchlist(id: int):
    conn = get_db()
    conn.execute("DELETE FROM watchlist WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"message": "Removed from watchlist"}

# ══════════════════════════════════════════════════════
#  PORTFOLIO CRUD
# ══════════════════════════════════════════════════════
@app.get("/portfolio")
def get_portfolio():
    conn  = get_db()
    rows  = conn.execute("SELECT * FROM portfolio ORDER BY added_at DESC").fetchall()
    conn.close()
    items = [dict(r) for r in rows]
    for item in items:
        try:
            info  = yf.Ticker(item["ticker"]).info
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            item["current_price"] = round(price, 2)
            item["market_value"]  = round(price * item["quantity"], 2)
            item["pnl"]           = round((price - item["buy_price"]) * item["quantity"], 2)
            item["pnl_pct"]       = round(((price - item["buy_price"]) / item["buy_price"]) * 100, 2)
        except:
            item["current_price"] = "N/A"
            item["market_value"]  = "N/A"
            item["pnl"]           = "N/A"
            item["pnl_pct"]       = "N/A"
    return items

@app.post("/portfolio")
def add_to_portfolio(item: PortfolioItem):
    conn = get_db()
    conn.execute(
        "INSERT INTO portfolio (ticker, quantity, buy_price) VALUES (?, ?, ?)",
        (item.ticker.upper(), item.quantity, item.buy_price)
    )
    conn.commit()
    conn.close()
    return {"message": f"{item.ticker.upper()} added to portfolio"}

@app.put("/portfolio/{id}")
def update_portfolio(id: int, item: PortfolioItem):
    conn = get_db()
    conn.execute(
        "UPDATE portfolio SET ticker=?, quantity=?, buy_price=? WHERE id=?",
        (item.ticker.upper(), item.quantity, item.buy_price, id)
    )
    conn.commit()
    conn.close()
    return {"message": "Portfolio item updated"}

@app.delete("/portfolio/{id}")
def delete_portfolio(id: int):
    conn = get_db()
    conn.execute("DELETE FROM portfolio WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"message": "Removed from portfolio"}

# ══════════════════════════════════════════════════════
#  ALERTS CRUD
# ══════════════════════════════════════════════════════
@app.get("/alerts")
def get_alerts():
    conn = get_db()
    rows = conn.execute("SELECT * FROM alerts ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/alerts")
def add_alert(item: AlertItem):
    if item.condition not in ("above", "below"):
        raise HTTPException(status_code=400, detail="Condition must be 'above' or 'below'")
    conn = get_db()
    conn.execute(
        "INSERT INTO alerts (ticker, target_price, condition) VALUES (?, ?, ?)",
        (item.ticker.upper(), item.target_price, item.condition)
    )
    conn.commit()
    conn.close()
    return {"message": f"Alert set for {item.ticker.upper()}"}

@app.put("/alerts/{id}")
def update_alert(id: int, item: AlertItem):
    conn = get_db()
    conn.execute(
        "UPDATE alerts SET ticker=?, target_price=?, condition=? WHERE id=?",
        (item.ticker.upper(), item.target_price, item.condition, id)
    )
    conn.commit()
    conn.close()
    return {"message": "Alert updated"}

@app.delete("/alerts/{id}")
def delete_alert(id: int):
    conn = get_db()
    conn.execute("DELETE FROM alerts WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"message": "Alert deleted"}

@app.get("/alerts/check")
def check_alerts():
    conn  = get_db()
    rows  = conn.execute("SELECT * FROM alerts WHERE triggered=0").fetchall()
    triggered = []
    for row in rows:
        try:
            info  = yf.Ticker(row["ticker"]).info
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            hit   = (row["condition"] == "above" and price >= row["target_price"]) or \
                    (row["condition"] == "below" and price <= row["target_price"])
            if hit:
                conn.execute("UPDATE alerts SET triggered=1 WHERE id=?", (row["id"],))
                triggered.append({"ticker": row["ticker"], "price": price, "target": row["target_price"]})
        except:
            pass
    conn.commit()
    conn.close()
    return {"triggered": triggered}

# ══════════════════════════════════════════════════════
#  STOCK PRICES CRUD
# ══════════════════════════════════════════════════════
@app.get("/prices")
def get_all_prices(ticker: Optional[str] = None):
    conn = get_db()
    if ticker:
        rows = conn.execute(
            "SELECT * FROM stock_prices WHERE ticker=? ORDER BY date DESC",
            (ticker.upper(),)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM stock_prices ORDER BY ticker, date DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/prices/{ticker}")
def get_prices_by_ticker(ticker: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM stock_prices WHERE ticker=? ORDER BY date DESC",
        (ticker.upper(),)
    ).fetchall()
    conn.close()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No saved prices for {ticker.upper()}")
    return [dict(r) for r in rows]

@app.post("/prices")
def add_price(item: StockPriceItem):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO stock_prices (ticker, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
            (item.ticker.upper(), item.date, item.open, item.high, item.low, item.close, item.volume)
        )
        conn.commit()
        conn.close()
        return {"message": f"Price for {item.ticker.upper()} on {item.date} saved"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail=f"Price for {item.ticker.upper()} on {item.date} already exists")

@app.post("/prices/fetch/{ticker}")
def fetch_and_save_prices(ticker: str, period: str = "1mo"):
    try:
        stock = yf.Ticker(ticker.upper())
        hist  = stock.history(period=period)
        if hist.empty:
            raise HTTPException(status_code=404, detail="No data found")
        conn    = get_db()
        saved   = 0
        skipped = 0
        for idx, row in hist.iterrows():
            try:
                conn.execute(
                    "INSERT INTO stock_prices (ticker, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
                    (ticker.upper(), str(idx.date()), round(row["Open"],2), round(row["High"],2),
                     round(row["Low"],2), round(row["Close"],2), int(row["Volume"]))
                )
                saved += 1
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
        conn.close()
        return {"message": f"Saved {saved} rows, skipped {skipped} duplicates for {ticker.upper()}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/prices/{id}")
def update_price(id: int, item: StockPriceItem):
    conn = get_db()
    conn.execute(
        "UPDATE stock_prices SET ticker=?, date=?, open=?, high=?, low=?, close=?, volume=? WHERE id=?",
        (item.ticker.upper(), item.date, item.open, item.high, item.low, item.close, item.volume, id)
    )
    conn.commit()
    conn.close()
    return {"message": "Price record updated"}

@app.delete("/prices/{id}")
def delete_price(id: int):
    conn = get_db()
    conn.execute("DELETE FROM stock_prices WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return {"message": "Price record deleted"}

@app.delete("/prices/ticker/{ticker}")
def delete_all_prices(ticker: str):
    conn = get_db()
    conn.execute("DELETE FROM stock_prices WHERE ticker=?", (ticker.upper(),))
    conn.commit()
    conn.close()
    return {"message": f"All prices for {ticker.upper()} deleted"}
