from bot.utils.constants import MIN_VALUE_ARA


def ara_hunter_filter(stock: dict) -> bool:
    price = stock.get("price")
    prev_price = stock.get("prev_price")
    open_price = stock.get("open")
    volume = stock.get("volume")
    value = stock.get("value")
    ma5 = stock.get("ma5")

    if not all([price, prev_price, open_price, volume, value, ma5]):
        return False

    prev_vol_approx = volume / max(stock.get("rel_vol", 1), 0.01)

    return (
        price > ma5
        and price > 1.05 * prev_price
        and price > open_price
        and volume > 0.2 * prev_vol_approx
        and value > MIN_VALUE_ARA
    )
