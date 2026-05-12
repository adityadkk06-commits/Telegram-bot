from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import yfinance as yf
import pandas as pd
import ta
import os

TOKEN = os.getenv("BOT_TOKEN")

# Daftar saham IHSG populer
stocks = [
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK",
    "ASII.JK", "ADRO.JK", "GOTO.JK", "MDKA.JK",
    "ANTM.JK", "CPIN.JK", "ICBP.JK", "INDF.JK",
    "AMMN.JK", "BRPT.JK", "PGEO.JK", "HUMI.JK",
    "MBMA.JK"
]

def analyze_stock(symbol):
    try:
        df = yf.download(symbol, period="3mo", interval="1d", auto_adjust=True)

        if df.empty or len(df) < 30:
            return None

        close = df["Close"].squeeze()

        ema9 = ta.trend.ema_indicator(close, window=9)
        ema21 = ta.trend.ema_indicator(close, window=21)
        rsi = ta.momentum.rsi(close, window=14)

        last_price = float(close.iloc[-1])
        last_ema9 = float(ema9.iloc[-1])
        last_ema21 = float(ema21.iloc[-1])
        last_rsi = float(rsi.iloc[-1])

        signal = None

        if last_ema9 > last_ema21 and last_rsi < 70:
            signal = "🟢 BUY"

        elif last_ema9 < last_ema21 and last_rsi > 30:
            signal = "🔴 SELL"

        if signal:
            return (
                f"{signal} {symbol}\n"
                f"Price: {last_price:.0f}\n"
                f"EMA9: {last_ema9:.0f}\n"
                f"EMA21: {last_ema21:.0f}\n"
                f"RSI: {last_rsi:.1f}"
            )

    except Exception as e:
        return f"Error {symbol}: {e}"

    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📈 Bot Scanner IHSG Aktif\n\n"
        "Command:\n"
        "/scan = scan saham"
    )
async def arahunter(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """
🔥 ARA HUNTER — IHSG Screener

Rules:
✅ Price > MA5
✅ Price > 1.05 x Previous Price
✅ Price > Open Price
✅ Volume > 0.2 x Previous Volume
✅ Value > 5B

Scanning saham IHSG...
"""

    await update.message.reply_text(text)
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Scanning IHSG...")

    results = []

    for stock in stocks:
        result = analyze_stock(stock)

        if result:
            results.append(result)

    if results:
        text = "\n\n".join(results[:10])
    else:
        text = "Tidak ada sinyal."

    await update.message.reply_text(text)

app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("scan", scan))

print("Bot IHSG running...")

app.run_polling()