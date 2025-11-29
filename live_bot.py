# ====================================================================
# ExpertOption Bot - Secure Trading Code
# File: live_bot.py  <-- تم تصحيح هذا السطر
# ====================================================================

# 1. Imports and Setup
import pandas as pd
import numpy as np
import time
import logging
import math
import getpass # Used for secure password input
from expertoption import ExpertOption 

# ---------- 🚨 Trading Settings (No Credentials Here) 🚨 ----------
ASSET_ID = "EURUSD"                     # Trading Asset
INTERVAL = 60                           # Candle duration in seconds (60s = 1 Minute)
TRADE_DURATION = 1                      # Trade duration (1 candle * 60s = 1 minute)
STAKE = 10.0                            # Amount to stake per trade
ACCOUNT_TYPE = 'demo'                   # 'demo' or 'real'
CANDLES_COUNT = 100                     # Number of candles required for calculation
# ----------------------------------------------------

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ---------- 2. Indicators and Signal Logic ----------

# Indicator Constants
FAST_MA = 12; SLOW_MA = 26; SIGNAL_MA = 9
RSI_PERIOD = 14; RSI_OVERSOLD = 30; RSI_OVERBOUGHT = 70
AO_SHORT = 5; AO_LONG = 34
SMA_SHORT = 14; SMA_LONG = 26

def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def macd(df, fast, slow, signal):
    fast_ema = ema(df['close'], fast)
    slow_ema = ema(df['close'], slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line

def rsi(series, period):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ma_up = up.rolling(window=period).mean()
    ma_down = down.rolling(window=period).mean()
    rs = ma_up / ma_down
    rsi = 100 - (100 / (1 + rs))
    return rsi

def awesome_oscillator(df, short, long):
    median = (df['high'] + df['low']) / 2.0
    ao = df['close'].rolling(window=short).mean() - df['close'].rolling(window=long).mean()
    return ao

def generate_signals(df):
    i = len(df) - 2 
    
    required_data = max(FAST_MA, SLOW_MA, RSI_PERIOD, AO_LONG, SMA_LONG)
    if i < required_data:
        logger.info(f"Insufficient data (need {required_data} candles, have {len(df)-1}).")
        return 'NO_ACTION'

    row = df.iloc[i]
    reason = []
    buy_score = 0
    sell_score = 0

    # MACD cross
    macd_val, macd_sig = df.at[i,'macd'], df.at[i,'macd_signal']
    prev_macd_val, prev_macd_sig = df.at[i-1,'macd'], df.at[i-1,'macd_signal']

    if prev_macd_val < prev_macd_sig and macd_val > macd_sig:
        buy_score += 1
        reason.append('MACD bullish cross')
    elif prev_macd_val > prev_macd_sig and macd_val < macd_sig:
        sell_score += 1
        reason.append('MACD bearish cross')

    # RSI levels
    if row['rsi'] < RSI_OVERSOLD:
        buy_score += 1
        reason.append('RSI oversold (<30)')
    elif row['rsi'] > RSI_OVERBOUGHT:
        sell_score += 1
        reason.append('RSI overbought (>70)')

    # SMA cross
    prev_short, prev_long = df.at[i-1,'sma14'], df.at[i-1,'sma26']
    curr_short, curr_long = df.at[i,'sma14'], df.at[i,'sma26']
    if prev_short < prev_long and curr_short > curr_long:
        buy_score += 1
        reason.append('SMA14 crossed above SMA26')
    elif prev_short > prev_long and curr_short < curr_long:
        sell_score += 1
        reason.append('SMA14 crossed below SMA26')

    if buy_score > sell_score and buy_score >= 2: 
        signal = 'CALL'
    elif sell_score > buy_score and sell_score >= 2:
        signal = 'PUT'
    else:
        signal = 'NO_ACTION'

    logger.info(f"Signal Check: CALL={buy_score}, PUT={sell_score} | Decision: {signal} ({'; '.join(reason)})")
    return signal

# ---------- 3. Data Fetching and Processing ----------
def get_processed_data(client):
    candles = client.get_candles(
        asset_id=ASSET_ID,
        interval=INTERVAL,
        count=CANDLES_COUNT
    )

    if not candles:
        logger.error("Failed to fetch candles. Check asset name or API connection.")
        return None

    df = pd.DataFrame(candles)
    df = df.rename(columns={'start': 'timestamp', 'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'volume': 'volume'})
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')

    # Calculate Indicators
    df['macd'], df['macd_signal'] = macd(df, FAST_MA, SLOW_MA, SIGNAL_MA)
    df['rsi'] = rsi(df['close'], RSI_PERIOD)
    df['ao'] = awesome_oscillator(df, AO_SHORT, AO_LONG)
    df['sma14'] = df['close'].rolling(window=SMA_SHORT).mean()
    df['sma26'] = df['close'].rolling(window=SMA_LONG).mean()

    return df

# ---------- 4. Main Execution Function ----------
def run_bot(client):
    try:
        df = get_processed_data(client)
        if df is None:
            return

        signal = generate_signals(df)
        
        if signal != 'NO_ACTION':
            logger.info(f"*** STRONG SIGNAL FOUND: {signal}! Placing trade... ***")
            
            exptime_seconds = TRADE_DURATION * INTERVAL 
            
            trade_result = client.buy(
                amount=STAKE,
                type=signal.lower(), 
                assetid=ASSET_ID,
                exptime=exptime_seconds,
                is_demo=1 if ACCOUNT_TYPE == 'demo' else 0 
            )

            if trade_result and trade_result.get('id'):
                logger.info(f"Trade successfully placed (ID: {trade_result.get('id')}) on {ASSET_ID}. Duration: {exptime_seconds}s.")
            else:
                logger.error(f"Trade failed to place. Response: {trade_result}")

        else:
            logger.info("No strong signal found. Waiting for next check.")

    except Exception as e:
        logger.error(f"An unexpected error occurred during execution: {e}")

# ---------- 5. Main Loop (Runs indefinitely in Colab) ----------
if __name__ == "__main__":
    logger.info("--- ExpertOption Bot Starting ---")
    
    # Secure Input for Credentials
    email = input("Please enter your Expert Option email: ")
    password = getpass.getpass("Please enter your Expert Option password: ")

    client = ExpertOption(email, password)

    if not client.login():
        logger.error("Login failed. Check credentials or network status.")
    else:
        logger.info(f"Login successful. Starting trading loop on {ASSET_ID}...")
        
        sleep_time = INTERVAL

        while True:
            run_bot(client)
            logger.info(f"Waiting for {sleep_time} seconds until the next check...")
            time.sleep(sleep_time)
