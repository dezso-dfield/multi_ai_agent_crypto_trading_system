import re, random, time

POS = {"moon","pump","breakout","bullish","rocket","win","long"}
NEG = {"dump","bearish","rug","short","liquidate","fear","crash"}

def toy_stream():
    """
    Fake sentiment stream. Yields dicts:
    {'ts': timestamp, 'text': str, 'score': float}
    """
    samples = [
        "BTC looks bullish, breakout soon?",
        "Funding too high, crash coming",
        "ETH on a rocket, careful at resistance",
        "Chop city. Staying flat.",
        "Bearish divergence on 4h, likely dump",
        "Macro improving, DXY down, risk on",
    ]
    while True:
        text = random.choice(samples)
        toks = re.findall(r"[a-z]+", text.lower())
        score = sum(1 for t in toks if t in POS) - sum(1 for t in toks if t in NEG)
        yield {"ts": time.time(), "text": text, "score": float(score)}
        time.sleep(0.5)

def headless_note():
    return "Replace toy_stream() with Playwright/Selenium or APIs (Reddit, Twitter, CryptoPanic)."