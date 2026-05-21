from bot.utils.constants import MIN_VALUE_BSJP


def bsjp_filter(stock: dict) -> bool:
    price = stock.get("price")
    prev_price = stock.get("prev_price")
    value = stock.get("value")
    volume = stock.get("volume")
    ma5 = stock.get("ma5")
    ma20 = stock.get("ma20")
    ma50 = stock.get("ma50")
    vol_ma20 = stock.get("vol_ma20")

    if not all([price, prev_price, value, volume, ma5, ma20, ma50, vol_ma20]):
        return False

    prev_vol_approx = volume / max(stock.get("rel_vol", 1), 0.01)

    return (
        value > MIN_VALUE_BSJP
        and volume > 1.2 * prev_vol_approx
        and price > ma20
        and ma20 > ma50
        and price > 1.01 * prev_price
        and price >= ma5
        and volume > 2 * vol_ma20
    )
