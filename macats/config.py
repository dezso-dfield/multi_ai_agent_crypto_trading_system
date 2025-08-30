# macats/config.py
from pydantic import BaseModel
import os
from dataclasses import dataclass

@dataclass
class Flags:
    USE_HEADLESS: bool = False
    USE_LIVE_EXCHANGE: bool = False

class Settings(BaseModel):
    symbol: str = os.getenv("SYMBOL", "BTC/USDT")
    paper_start_balance: float = float(os.getenv("PAPER_START_BALANCE", 10000))
    execution_mode: str = os.getenv("EXECUTION_MODE", "paper")  # paper|live
    timeframe: str = os.getenv("TIMEFRAME", "1h")
    base_currency: str = os.getenv("BASE_CURRENCY", "USDT")
    max_leverage: float = float(os.getenv("MAX_LEVERAGE", 1))
    exchange_id: str = os.getenv("EXCHANGE_ID", "binance")
    api_key: str = os.getenv("API_KEY", "")
    api_secret: str = os.getenv("API_SECRET", "")
    password: str = os.getenv("PASSWORD", "")

FLAGS = Flags()
SETTINGS = Settings()