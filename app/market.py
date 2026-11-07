import time
import pandas as pd
import yfinance as yf

_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}
TTL = 900  # seconds; yfinance data is delayed anyway


def prices(tickers: list[str], start: str) -> pd.DataFrame:
    """Adjusted close prices, columns = tickers, index = date."""
    key = (tuple(sorted(tickers)), start)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    df = yf.download(list(key[0]), start=start, auto_adjust=True, progress=False)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(key[0][0])
    df = df.ffill().dropna(how="all")
    missing = [t for t in tickers if t not in df.columns or df[t].isna().all()]
    if missing:
        raise ValueError(f"No market data for: {', '.join(missing)}")
    _CACHE[key] = (time.time(), df)
    return df
