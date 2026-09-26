import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def js(payload: dict):
    r = subprocess.run(["node", str(ROOT / "tests" / "js_bridge.js")], input=json.dumps(payload),
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


@pytest.fixture
def run_js():
    return js


# A small ticker map so parser tests don't depend on the live SEC/Nasdaq files.
MINI_MAP = {
    "AAPL": ["Apple Inc.", "S", 320193, 1],
    "APLE": ["Apple Hospitality REIT, Inc.", "S", 1418121, 1],
    "MSFT": ["MICROSOFT CORP", "S", 789019, 1],
    "BRK-A": ["BERKSHIRE HATHAWAY INC", "S", 1067983, 1],
    "BRK-B": ["BERKSHIRE HATHAWAY INC", "S", 1067983, 1],
    "TSLA": ["Tesla, Inc.", "S", 1318605, 1],
    "SPY": ["State Street SPDR S&P 500 ETF Trust", "E", None, None],
    "VOO": ["Vanguard S&P 500 ETF", "E", None, None],
    "FOX": ["Fox Corp", "S", 1754301, 1],
    "FOXA": ["Fox Corp", "S", 1754301, 1],
    "NMAX": ["Newsmax Inc.", "S", 2026478, 1],
    "SHOP": ["SHOPIFY INC.", "S", 1594805, 1],
    "GOOG": ["Alphabet Inc.", "S", 1652044, 1],
    "GOOGL": ["Alphabet Inc.", "S", 1652044, 1],
    "GOOGM": ["Alphabet Inc.", "S", 1652044, 0],
    "XYZ": ["Block, Inc.", "S", 1512673, 1],
    "NYT": ["NEW YORK TIMES CO", "S", 71691, 1],
    "TRI": ["THOMSON REUTERS CORP /CAN/", "S", 1075124, 1],
    "QQQ": ["Invesco QQQ Trust, Series 1", "E", None, None],
}


@pytest.fixture
def mini_map():
    return MINI_MAP
