import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    # API Keys
    FRED_API_KEY: str = os.getenv("FRED_API_KEY", "")
    
    # FRED Series IDs
    FRED_10Y_TREASURY: str = "DGS10"
    FRED_2Y_TREASURY:  str = "DGS2"
    FRED_FED_FUNDS:    str = "FEDFUNDS"
    FRED_HY_SPREAD:    str = "BAMLH0A0HYM2"
    FRED_IG_SPREAD:    str = "BAMLC0A0CM"
    FRED_VIX:          str = "VIXCLS"
    FRED_REAL_10Y:     str = "DFII10"
    FRED_CPI:          str = "CPIAUCSL"
    
    # Yahoo Finance Tickers
    SPY_TICKER:  str = "SPY"
    RSP_TICKER:  str = "RSP"
    QQQ_TICKER:  str = "QQQ"
    NVDA_TICKER: str = "NVDA"
    
    # Scoring Weights (총합=100)
    W_LIQUIDITY: float = 30.0
    W_RATES:     float = 25.0
    W_CREDIT:    float = 25.0
    W_IPO:       float = 20.0
    
    # Output
    OUTPUT_PATH: str = "data/latest_scores.json"

config = Config()
