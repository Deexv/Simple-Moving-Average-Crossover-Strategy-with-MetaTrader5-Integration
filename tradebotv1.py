import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import time
import sys

# Connect Python to MetaTrader5
mt5.initialize()

# Strategy parameters
SYMBOL = "GBPUSD DFX 10 Index"  # Replace with your desired symbol
VOLUME = 0.2
TIMEFRAME = mt5.TIMEFRAME_M1
SMA_PERIOD = 10
DEVIATION = 20
TICKET = 0  # Initialize the TICKET variable

# Trail SL parameters
MAX_DIST_SL = 0.0006  # Max distance between current price and SL, otherwise SL will update
TRAIL_AMOUNT = 0.0003  # Amount by which SL updates
DEFAULT_SL = 0.0003  # If position has no SL, set a default SL

# Global variables
tick_count = 0
ticket_ids = []

# Function to send a market order
def market_order(symbol, volume, order_type, **kwargs):
    tick = mt5.symbol_info_tick(symbol)

    order_dict = {'buy': mt5.ORDER_TYPE_BUY, 'sell': mt5.ORDER_TYPE_SELL}
    price_dict = {'buy': tick.ask, 'sell': tick.bid}

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_dict[order_type],
        "price": price_dict[order_type],
        "deviation": DEVIATION,
        "magic": 100,
        "comment": "python market order",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    order_result = mt5.order_send(request)
    print(order_result)

    return order_result

# Function to close an order based on ticket id
def close_order(ticket):
    positions = mt5.positions_get()

    for pos in positions:
        if pos.ticket == ticket:
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket,
                "type": pos.type,  # Close position by sending an opposite order
                "volume": pos.volume,
            }

            result = mt5.order_send(request)
            print(result)

            return result

    return 'Ticket does not exist'

# Function to get the exposure of a symbol
def get_exposure(symbol):
    positions = mt5.positions_get(symbol=symbol)
    if positions:
        pos_df = pd.DataFrame(positions, columns=positions[0]._asdict().keys())
        exposure = pos_df['volume'].sum()
        return exposure

# Function to look for trading signals
def signal(symbol, timeframe, sma_period):
    bars = mt5.copy_rates_from_pos(symbol, timeframe, 1, sma_period)
    bars_df = pd.DataFrame(bars)

    last_close = bars_df.iloc[-1].close
    sma = bars_df.close.mean()

    direction = 'flat'
    if last_close > sma:
        direction = 'buy'
    elif last_close < sma:
        direction = 'sell'

    return last_close, sma, direction

# Function to trail SL
def trail_sl(ticket_id):
    # Get position based on ticket_id
    position = mt5.positions_get(ticket=ticket_id)

    # Check if position exists
    if position:
        position = position[0]
    else:
        print('Position does not exist')
        sys.exit()

    # Get position data
    order_type = position.type
    price_current = position.price_current
    sl = position.sl

    dist_from_sl = abs(round(price_current - sl, 6))

    if dist_from_sl > MAX_DIST_SL:
        # Calculate new SL
        if sl != 0.0:
            if order_type == mt5.ORDER_TYPE_BUY:  # BUY position
                new_sl = price_current - TRAIL_AMOUNT
            elif order_type == mt5.ORDER_TYPE_SELL:  # SELL position
                new_sl = price_current + TRAIL_AMOUNT
        else:
            # Set default SL if there is no SL on the symbol
            new_sl = price_current - DEFAULT_SL if order_type == mt5.ORDER_TYPE_BUY else price_current + DEFAULT_SL

        request = {
            'action': mt5.TRADE_ACTION_SLTP,
            'position': position.ticket,
            'sl': new_sl,
        }

        result = mt5.order_send(request)
        print(result)
        return result

# Main program
if __name__ == '__main__':
    print('Starting Simple Moving Average Crossover Strategy..')

    while True:
        # Calculating account exposure
        exposure = get_exposure(SYMBOL)

        # Calculating last candle close and simple moving average and checking for trading signal
        last_close, sma, direction = signal(SYMBOL, TIMEFRAME, SMA_PERIOD)

        # Trading logic
        if direction == 'buy':
            # Close all short positions
            for pos in mt5.positions_get():
                if pos.type == mt5.ORDER_TYPE_SELL:  # SELL position
                    close_order(pos.ticket)

            # If there are no open positions or opposite positions, open a new long position
            opposite_positions = [pos for pos in mt5.positions_get() if pos.type == mt5.ORDER_TYPE_BUY]  # BUY positions
            if not mt5.positions_total() or opposite_positions:
                # Close opposite positions
                for pos in opposite_positions:
                    close_order(pos.ticket)
                market_order(SYMBOL, VOLUME, direction)

        elif direction == 'sell':
            # Close all long positions
            for pos in mt5.positions_get():
                if pos.type == mt5.ORDER_TYPE_BUY:  # BUY position
                    close_order(pos.ticket)

            # If there are no open positions or opposite positions, open a new short position
            opposite_positions = [pos for pos in mt5.positions_get() if pos.type == mt5.ORDER_TYPE_SELL]  # SELL positions
            if not mt5.positions_total() or opposite_positions:
                # Close opposite positions
                for pos in opposite_positions:
                    close_order(pos.ticket)
                market_order(SYMBOL, VOLUME, direction)

        print('Time:', datetime.now())
        print('Exposure:', exposure)
        print('Last Close:', last_close)
        print('SMA:', sma)
        print('Signal:', direction)
        print('-------\n')

        # Trail Stop Loss for all open positions
        for ticket in mt5.positions_get():
            ticket_ids.append(ticket.ticket)
            trail_sl(ticket.ticket)

        # Wait for price update
        time.sleep(1)
