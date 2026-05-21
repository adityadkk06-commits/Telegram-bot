from bot.utils.constants import MIN_VALUE_BIG


def big_accumulation_filter(stock: dict) -> bool:
    price = stock.get("price")
    prev_price = stock.get("prev_price")
    value = stock.get("value")
    ma20 = stock.get("ma20")
    ma50 = stock.get("ma50")
    vol_ma5 = stock.get("vol_ma5")
    vol_ma20 = stock.get("vol_ma20")
    bandar_score = stock.get("bandar_score")

    if not all([price, prev_price, value, ma20, ma50, vol_ma5, vol_ma20]):
        return False
    if bandar_score is None:
        return False

    return (
        bandar_score > 25
        and value > MIN_VALUE_BIG
        and ma20 > ma50
        and price < 500
        and vol_ma5 > 1.3 * vol_ma20
        and price > prev_price
    )
