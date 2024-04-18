import alpaca_trade_api as tradeapi
from datetime import datetime, timedelta
import pandas as pd
import pytz
import time
import copy
import robin_stocks.robinhood as r
from secret import *

#global vars
all_codes = []
data = []
current_holdings = []
orders_to_check = {}
current_holdings_data = {}
current_balance = 0.0
recent_sells = {}

test_buy = False

wins = 0
losses = 0
deaths = 0

def log_in_to_alpaca():
    # Initialize the Alpaca API client
    api = tradeapi.REST(ALPACA_KEY, ALPACA_SECRET, 'https://paper-api.alpaca.markets', api_version='v2')
    login = r.login(USERNAME, PASSWORD)
    return api

def get_init_data(api, time_interval, total_time):

    global data
    global all_codes

    data = [0] * int(total_time / time_interval)

    # get codes
    assets = api.list_assets(asset_class='crypto')
    tradable_usd_assets = [asset for asset in assets if asset.tradable and asset.symbol.endswith('/USD')]
    
    # print("alpaca cryptos")
    alpaca_codes = []
    for asset in tradable_usd_assets:
        alpaca_codes.append(asset.symbol)

    #print("robinhood codes")
    robinhood_codes = []
    for c in r.crypto.get_crypto_currency_pairs():
        robinhood_codes.append(c['asset_currency']['code'] + "/USD")

    #print(robinhood_codes)

    all_codes = []
    for c in alpaca_codes:
        if c in robinhood_codes:
            all_codes.append(c)

    #print("all codes: ")
    #print(all_codes)

        

    

    

    # set data
    for i in range(len(data)):

        crypto_prices = {}

        # account for time taken to do this
        start = time.time()
        for code in all_codes:
            crypto_prices[code] = float(get_current_crypto_price(code))
        end = time.time()
        elapsed = end - start

        data[i] = crypto_prices
        print("Time " + str(i + 1) + "/" + str(len(data)) + " logged.")

        #wait for time period
        time.sleep(max(time_interval - elapsed, 0))

    print("Log set.\n")
    print(get_elapsed_prices("USDC/USD"))



def update_log(api):

    global data
    
    #remove oldest (first) column, add new column at the end
    data.pop(0)

    #get new data
    crypto_prices = {}

    # account for time taken to do this
    start = time.time()
    for code in all_codes:
        crypto_prices[code] = float(get_current_crypto_price(code))
    end = time.time()
    elapsed = end - start

    data.append(crypto_prices)


def get_elapsed_prices(symbol):

    global data

    toret = []
    for i in range(len(data)):
        toret.append(data[i][symbol])

    return toret
    
def get_local_mins(prices):

    toret = []

    for i in range(1,len(prices)-1):
        if prices[i] < prices[i-1] and prices[i] < prices[i+1] and prices[i] not in toret:
            toret.append(prices[i])

    #check first and last
    if prices[0] < prices[1] and prices[0] not in toret:
        toret.insert(0, prices[0])
    if prices[len(prices)-1] < prices[len(prices)-2] and prices[len(prices)-1] not in toret:
        toret.append(prices[len(prices)-1])

    return toret


def get_local_maxs(prices):

    toret = []

    for i in range(1,len(prices)-1):
        if prices[i] > prices[i-1] and prices[i] > prices[i+1] and prices[i] not in toret:
            toret.append(prices[i])

    #check first and last
    if prices[0] > prices[1] and prices[0] not in toret:
        toret.insert(0, prices[0])
    if prices[len(prices)-1] > prices[len(prices)-2] and prices[len(prices)-1] not in toret:
        toret.append(prices[len(prices)-1])

    return toret

def uptrend(prices):

    return prices[len(prices)-1] > prices[len(prices)-2]

def volatile(local_mins, local_maxes):

    return len(local_mins) >= 3 and len(local_maxes) >= 3

def get_growth_rate(prices):

    return prices[len(prices)-1] / prices[len(prices)-2]

def buy_crypto(api, symbol, shares):

    try:
        order = api.submit_order(
            symbol=symbol,
            qty=shares,
            side='buy',
            type='market',
            time_in_force='ioc',
            order_class='simple'
        )
        return order
    except Exception as e:
        print(f"Error BUYING {symbol}: {e}")
        return None


def determine_if_buy(prices, window, symbol, entry_price, exit_price, local_mins, local_maxs):

    global test_buy
    global orders_to_check
    global current_holdings_data

    PRINT_VERSION = True

    #structured to see what kept crypto from being bought
    buy = True

    if PRINT_VERSION:

        if exit_price / entry_price <= 1.0025:
            print(symbol + ": Window not wide enough")
            buy = False

        if window <= 0:
            print(symbol + ": Negative window")
            buy = False

        if symbol in current_holdings_data:
            print(symbol + ": Already purchased")
            buy = False

        if prices[len(prices)-1] < entry_price:
            print(symbol + ": Price too low")
            buy = False

        if prices[len(prices)-1] > exit_price:
            print(symbol + ": Price too high")
            buy = False

        if not uptrend(prices):
            print(symbol + ": Not in uptrend")
            buy = False

        if not volatile(local_mins, local_maxs):
            print(symbol + ": Not volatile enough")
            buy = False

        if symbol in orders_to_check.keys():
            print(symbol + ": Already considering crypto")
            buy = False

        return buy
    
    return (window > 0 and symbol not in current_holdings_data and exit_price / entry_price > 1.0025 and prices[len(prices)-1] >= entry_price and prices[len(prices)-1] <= exit_price and uptrend(prices) and volatile(local_mins, local_maxs) and symbol not in orders_to_check.keys()) or test_buy


def determine_cryptos_to_buy(api, data):

    global current_holdings
    global current_holdings_data
    global current_balance
    global orders_to_check
    global all_codes

    orders = []

    for symbol in all_codes:

        #defining trading terms
        prices = get_elapsed_prices(symbol)

        lows = get_local_mins(prices)
        highs = get_local_maxs(prices)

        mean_high = sum(highs) / (len(highs) + 0.00000000000000001)
        mean_low = sum(lows) / (len(lows) + 0.00000000000000001)

        if len(highs) == 0 or len(lows) == 0:
            print("woah woah woah")
            continue

        min_high = min(highs)
        max_low = max(lows)

        my_high = (mean_high + min_high)/2
        my_low = (mean_low + max_low)/2

        window = my_high - my_low

        entry_price = my_low
        exit_price = my_high

        current_price = prices[len(prices)-1]

        if determine_if_buy(prices=prices, window=window, symbol=symbol, entry_price=entry_price, exit_price=exit_price, local_mins=lows, local_maxs=highs):

            amount_to_spend = min(min((current_balance / 25) + (get_growth_rate(prices) * 10), get_current_buying_power(api)), 1000)

            number_of_shares = amount_to_spend/entry_price

            #buy the crypto
            order = buy_crypto(api, symbol, number_of_shares)

            #update data structure too
            current_holdings = get_current_holdings(api)
            current_balance = get_current_balance(api)

            #update records
            if order:
                orders_to_check[symbol] = order
                current_holdings_data[symbol] = {}
                current_holdings_data[symbol]["status"] = order.status
                current_holdings_data[symbol]["goal_sell_price"] = exit_price
              


def sell_crypto(api, symbol, shares):

    #adjust for Alpaca's stealing from me :(
    shares *= 0.9974

    try:
        order = api.submit_order(
            symbol=symbol,
            qty=shares,
            side='sell',
            type='market',
            time_in_force='ioc',
            order_class='simple'
        )
        return order
    except Exception as e:
        print(f"Error SELLING {symbol}: {e}")
        return None

def determine_if_sell(current_price, goal_sell_price, life_time, stop_loss):

    death_time = 5
    global deaths

    if life_time > death_time:
        deaths += 1

    return (((current_price != None) and (current_price > goal_sell_price or life_time > death_time or current_price < stop_loss)) and life_time > 0)

def determine_cryptos_to_sell(api):

    global current_holdings
    global current_holdings_data
    global current_balance
    global recent_sells

    my_holdings = copy.deepcopy(current_holdings_data).keys()

    for symbol in my_holdings:

        current_price = get_current_crypto_price(symbol)
        buy_price = current_holdings_data[symbol]["buy_price"]
        goal_sell_price = current_holdings_data[symbol]["goal_sell_price"]
        shares = current_holdings_data[symbol]["shares"]
        life_time = current_holdings_data[symbol]["life_time"]
        stop_loss = current_holdings_data[symbol]["stop_loss"]

   

        if current_price == None or buy_price == None or goal_sell_price == None or shares == None or stop_loss == None:
            continue

        #selling for profit OR for life time
        if determine_if_sell(current_price=current_price, goal_sell_price=goal_sell_price, life_time=life_time, stop_loss=stop_loss):

            #sell action
            order = sell_crypto(api, symbol, shares)

            #if successfully sold...
            if order:

                #update stats
                recent_sells[symbol] = {}
                recent_sells[symbol]["order"] = order
                recent_sells[symbol]["buy_price"] = current_holdings_data[symbol]["buy_price"]

                del current_holdings_data[symbol]

                


        # adjust stop loss
        elif current_price >= (goal_sell_price - ((goal_sell_price - buy_price)/2)):

            current_holdings_data[symbol]["stop_loss"] = current_price

                
# check to see if orders successfully filled
def update_current_holdings(api):

    global current_holdings
    global current_holdings_data
    global orders_to_check

    #copy orders_to_check keys
    temp_keys = []
    for k in orders_to_check.keys():
        temp_keys.append(k)

    for symbol in temp_keys:

        order_id = orders_to_check[symbol].id

        #get (potentially) new version of order
        new_order = api.get_order(order_id)

        order_status = new_order.status

        # order is good, transition to data structure
        if(order_status == 'filled'):

            print("Purchased " + str(new_order.filled_qty) + " shares of " + symbol)

            current_holdings_data[symbol]["status"] = "filled"
            current_holdings_data[symbol]["buy_price"] = float(new_order.filled_avg_price)
            current_holdings_data[symbol]["stop_loss"] = float(new_order.filled_avg_price)
            current_holdings_data[symbol]["shares"] = float(new_order.filled_qty)
            current_holdings_data[symbol]["life_time"] = 0

            del orders_to_check[symbol]

        elif order_status == 'canceled' or order_status == 'rejected' or order_status == 'expired':

            del orders_to_check[symbol]
            del current_holdings_data[symbol]

        else:

            print("Still haven't heard anything... :(")


def update_recent_sells(api):

    global recent_sells
    global wins
    global losses

    temp_keys = []
    for k in recent_sells.keys():
        temp_keys.append(k)

    for symbol in temp_keys:

        order_id = recent_sells[symbol]["order"].id

        #get (potentially) new version of order
        new_order = api.get_order(order_id)

        order_status = new_order.status

        if(order_status == 'filled'):

            print("Sold " + str(new_order.filled_qty) + " shares of " + symbol)

            delta = (float(new_order.filled_avg_price) - float(recent_sells[symbol]["buy_price"])) * float(new_order.filled_qty)

            if delta > 0:
                wins += 1
                print("Profit: " + "$" + str(delta))
            else:
                losses += 1
                print("Loss: " + "$" + str(delta))

            del recent_sells[symbol]



def age_holdings():

    global current_holdings_data

    for symbol in current_holdings_data.keys():

        if current_holdings_data[symbol]["status"] == "filled":

            current_holdings_data[symbol]["life_time"] += 1




def get_current_crypto_price(symbol):

    adjusted_code = symbol.split('/')[0]

    return float(r.crypto.get_crypto_quote(adjusted_code)['mark_price'])

    try:
        # Fetch the most recent bar for the cryptocurrency
        bars = api.get_crypto_bars(symbol, timeframe="1Min", limit=1).df
        if not bars.empty:
            # Assuming the latest bar is the most recent price
            latest_price = bars['close'].iloc[-1]
            return float(latest_price)
        else:
            print(f"No data found for {symbol}")
            return None
    except Exception as e:
        print(f"Error fetching current price for {symbol}: {e}")
        return None


def get_current_holdings(api):

    owned_cryptos = []
    try:
        positions = api.list_positions()
        for position in positions:
            # Assuming all crypto symbols in Alpaca include a '/' (e.g., 'BTC/USD')
            if '/' in position.symbol:
                owned_cryptos.append(position.symbol)
    except Exception as e:
        print(f"Error fetching positions: {e}")
    
    return owned_cryptos
        
    
def get_current_balance(api):

    try:
        account = api.get_account()
        return float(account.cash)
    except Exception as e:
        print(f"Error fetching account information: {e}")
        return None
    
def get_current_buying_power(api):

    try:
        account = api.get_account()
        return float(account.buying_power)
    except Exception as e:
        print(f"Error fetching account information: {e}")
        return None




def run():

    #algorithm settings
    CHECK_SELL_TIME = 3   # seconds
    CHECK_BUY_TIME = 15   # seconds
    TOTAL_TIME = 150      # seconds

    #global vars
    global data
    global current_holdings
    global orders_to_check
    global current_holdings_data
    global current_balance

    global wins
    global losses
    global deaths

    api = log_in_to_alpaca()

    counter = 0
    get_init_data(api, CHECK_BUY_TIME, TOTAL_TIME)

    while True:

        # get recent data
        if counter % CHECK_SELL_TIME == 0:
            current_holdings = get_current_holdings(api)
            current_balance = get_current_balance(api)

        if counter % CHECK_BUY_TIME == 0:
            update_log(api)
            determine_cryptos_to_buy(api, data)

        if counter % CHECK_SELL_TIME == 0:

            age_holdings()
            update_current_holdings(api)
            update_recent_sells(api)
            determine_cryptos_to_sell(api)

        time.sleep(1)


        counter += 1

        #reset counter
        if counter == int(TOTAL_TIME):
            print("Wins: " + str(wins))
            print("Losses: " + str(losses))
            print("Deaths: " + str(deaths))
            counter = 0


    determine_cryptos_to_buy(data)
    #print(data["BTC/USD"])

run()
