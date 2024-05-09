import numpy as np
import pandas as pd
import requests
import datetime

from enum import Enum
from Historic_Crypto import HistoricalData
from scipy.stats import norm

################################################
# Miscellaneous
################################################
days_per_year = 365
hours_per_year = 24 * days_per_year
seconds_per_year = hours_per_year * 60 * 60

DERIBIT_API_URL = "https://deribit.com/api/v2/"

def cumsum_list(lists):   
    cum_list = []   
    l = len(lists)   
    cum_list = [sum(lists[0:x:1]) for x in range(0, l+1)]
    return cum_list[1:]

################################################
# Symbols
################################################
class Ticker(str, Enum):
    AVAX = 'AVAX'
    ETH = 'ETH'
    BTC = 'BTC'

    def __str__(self):
        return f"{self.value}"
    
    @staticmethod
    def cast(ticker):
        try:
            return Ticker(ticker.upper())
        except:
            raise Exception(f"Unsupported ticker '{ticker}'")

deribit_symbols = [Ticker.ETH, Ticker.BTC]
binance_symbols = {Ticker.AVAX: "AVAXUSDT", Ticker.ETH: "ETHUSDT", Ticker.BTC: "BTCUSDT"}
coingecko_ids = {Ticker.AVAX: "avalanche-2", Ticker.ETH: "ethereum", Ticker.BTC: "bitcoin"}
historic_ids = {Ticker.AVAX: "AVAX-USD", Ticker.ETH: "ETH-USD", Ticker.BTC: "BTC-USD"}

################################################
# Spot & Option Data Retrieval
################################################
def get_underlier_price(ticker: str):
    """
        Get spot price of underlying asset from Binance (or CryptoWatch if rate limit is reached).

        INPUTS:
            ticker - Symbol of underlying asset.

        OUTPUTS:
            Spot price of specified underlying asset.
    """

    # Cast ticker to enum type
    ticker = Ticker.cast(ticker)

    # Using Binance API to get latest price
    response = requests.get(
        f"https://api.binance.com/api/v3/ticker/price?symbol={binance_symbols[ticker]}"
    )
    response_json = response.json()
    # If Binance tells us we have been making too many requests, use Cryptowatch
    if 'code' in response_json and response_json['code'] == -1003:
        # Use CryptoWatch API to get latest price
        response = requests.get(
            f"https://api.cryptowat.ch/markets/binance/{binance_symbols[ticker]}/price"
        )

        try:
            spot_price = float(response.json()['result']['price'])
        except:
            raise Exception("Could not retrieve underlying spot price from Cryptowatch.")
    else:
        try:
            spot_price = float(response.json()['price'])
        except:
            raise Exception("Could not retrieve underlying spot price from Binance.")

    return spot_price

def get_historical_prices(ticker: Ticker, sampling_freq = 1, steps = 1e3):

    steps = steps + 1
    # sampling_freq = 1 # hours
    sampling_freq_in_seconds = int(1 * 60 * 60)

    hour_steps = steps * sampling_freq
    end_date = datetime.datetime.today()
    end_date.replace(minute=0, second=0, microsecond=0)
    start_date = datetime.datetime.today() - datetime.timedelta(hours=hour_steps)
    end_date = end_date.strftime("%Y-%m-%d-%H") + "-00"
    start_date = start_date.strftime("%Y-%m-%d-%H") + "-00"

    prices = pd.DataFrame()
    prices = HistoricalData(historic_ids[ticker], sampling_freq_in_seconds, start_date, end_date, verbose = False).retrieve_data()

    prices = prices['close'].to_numpy()
    prices = prices[0::sampling_freq]

    return prices

def deribit_option_data(ticker, utcnow):
    # Construct parameters for getting all instruments from Deribit's API
    get_instruments_api_params = {
        "currency": ticker,
        "kind": "option",
        "expired": "false"
    }

    try:
        get_instruments_api_response = requests.get(DERIBIT_API_URL + '/public/get_instruments', get_instruments_api_params)
        get_instruments_json = get_instruments_api_response.json()
        instruments = get_instruments_json['result']
    except:
        raise Exception("There was an error collecting instrument data from Deribit")

    num_fridays_to_look_ahead = 52 # Number of Fridays to look ahead to
    seconds_per_week = 7 * 24 * 60 * 60
    day_number = utcnow.weekday()
    # Get date of next Friday (if it is a Friday, next weeks Friday)
    if day_number >= 4:
        first_friday = int((utcnow.replace(hour=8, minute=0, second=0, microsecond=0) + datetime.timedelta(days=-day_number, weeks=1) + datetime.timedelta(days=4)).timestamp())
    elif day_number < 4:
        first_friday = int((utcnow.replace(hour=8, minute=0, second=0, microsecond=0) - datetime.timedelta(days=day_number) + datetime.timedelta(days=4)).timestamp())

    # Get expirations for num_fridays_to_look_ahead following the friday closest to today
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

    expiration_strings = set()
    for j in range(num_fridays_to_look_ahead):
        ts = datetime.datetime.utcfromtimestamp(first_friday + j*seconds_per_week)
        day = ts.day
        month = months[ts.month-1]
        year = f'{ts.year}'[2:]
        hrexpiration = f'{day}{month}{year}'
        expiration_strings.add(hrexpiration)

    # Arrays for tracking quote data
    log_moneynesses = []
    expiration_datetimes = [] # Set of all expirations
    yearly_times_to_expiration = [] # Set of all times to expiration
    strikes = []
    contract_types = []
    spot_prices = []
    yearly_mark_implied_volatilities = []
    mark_prices = []
    prices = []

    # Loop through all instruments for the specified ticker
    for instrument in instruments:
        # Split instrument name into costituent parts
        split_instrument_name = instrument['instrument_name'].split('-')
        expiration_string = split_instrument_name[1] # Extract expiration string

        # If expiration of current instrument is not one of the expirations we are looking for, continue to next instrument
        if expiration_string not in expiration_strings: 
            continue

        # Construct order book parameters for API request
        order_book_api_params = {
            "instrument_name": instrument['instrument_name'],
            "depth": 1 # Taken out of a hat
        }

        # Attempt to retrieve response from API request. Proceed to next instrument if there is an error
        try:
            order_book_api_response = requests.get(DERIBIT_API_URL + "/public/get_order_book", order_book_api_params)
            order_book_json = order_book_api_response.json()
        except Exception as e: # Check for API response exception
            print(f"Error getting book data for instrument \"{instrument['instrument_name']}\": {e}")
            continue # Proceed to next instrument if error with current one
        
        # Extract data into more readable variables
        expiration_timestamp_millis = instrument['expiration_timestamp'] # Expiration in milliseconds
        expiration_timestamp_seconds = expiration_timestamp_millis / 10**3
        tte_in_millis = expiration_timestamp_millis - (utcnow.timestamp() * 10**3)
        tte_in_seconds = tte_in_millis / 10**3
        tte_in_years = tte_in_seconds / seconds_per_year
        expiration = datetime.datetime.utcfromtimestamp(expiration_timestamp_seconds)
        strike = float(split_instrument_name[2])
        contract_type = split_instrument_name[-1] # Extract contract type string ("P" or "C")

        # Get underlying price from deribit quote data and compute moneyness/log moneyness
        spot_price = order_book_json['result']['underlying_price']
        log_moneyness = np.log(strike / spot_price)

        # Implied volatility from Deribit is yearly as percent (if yearly vol is 0.12, it comes back as 12)
        yearly_mark_implied_volatility = order_book_json['result']['mark_iv'] / 100
        
        # Option Price denominated in Token & Usd
        mark_price = order_book_json['result']['mark_price']
        price = mark_price * spot_price

        # Update arrays/sets to include relevant information
        expiration_datetimes.append(expiration)
        yearly_times_to_expiration.append(tte_in_years)
        strikes.append(strike)
        log_moneynesses.append(log_moneyness)
        contract_types.append(contract_type)
        spot_prices.append(spot_price)
        yearly_mark_implied_volatilities.append(yearly_mark_implied_volatility)
        mark_prices.append(mark_price)
        prices.append(price)

    # Cast all arrays to numpy arrays for computational conveniences
    expiration_datetimes = np.array(expiration_datetimes)
    yearly_times_to_expiration = np.array(yearly_times_to_expiration)
    strikes = np.array(strikes)
    log_moneynesses = np.array(log_moneynesses)
    contract_types = np.array(contract_types)
    spot_prices = np.array(spot_prices)
    yearly_mark_implied_volatilities = np.array(yearly_mark_implied_volatilities)
    mark_prices = np.array(mark_prices)
    prices = np.array(prices)

    return (
        expiration_datetimes,
        yearly_times_to_expiration,
        strikes,
        log_moneynesses,
        contract_types,
        spot_prices,
        yearly_mark_implied_volatilities,
        mark_prices,
        prices
    )

################################################
# Option Formulas
################################################
N = norm.cdf

def bs_call(S, K, T, r, sigma):
    d1 = (np.log(S/K) + (r + sigma**2/2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * N(d1) - K * np.exp(-r*T)* N(d2)

def bs_put(S, K, T, r, sigma):
    d1 = (np.log(S/K) + (r + sigma**2/2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma* np.sqrt(T)
    return K*np.exp(-r*T)*N(-d2) - S*N(-d1)

def binary_vol_finder(contract_type,option_price,spot_price,strike,T,r):

    sigma_bounds = np.arange(0.01, 2, 0.0001)
    """ Perform Binary Search """

    left, right = 0, len(sigma_bounds) - 1
    while left <= right:
        # Get midpoint of indices
        mid = (left + right) // 2 # double forward slash means integer division
        _iv = sigma_bounds[mid]

        # Compute the option price using sigma at the `mid` index
        if contract_type == 'C':
            _option_price = bs_call(spot_price, strike, T, r, _iv)
        else: # Put
            _option_price = bs_put(spot_price, strike, T, r, _iv)

        # Check if the computed option price is within some threshold of the true option price
        # If the computed option price is smaller, the sigma must be increased, so we move `left` above `mid`
        # If the computed option price is larger, the sigma must be decreased, so we move `right` below `mid`
        if abs(_option_price - option_price) < 1e-8:
            return sigma_bounds[mid]
        elif _option_price < option_price:
            left = mid + 1
        else:
            right = mid - 1

    # Compute the option price using sigma at the `mid` index
    _iv = sigma_bounds[right]
    if contract_type == 'C':
        _option_price = bs_call(spot_price, strike, T, r, _iv)
    else: # Put
        _option_price = bs_put(spot_price, strike, T, r, _iv)

    # If we are here, then we have searched the whole sigma space
    # and nothing was within the threshold of the true option price.
    # At this point, left > right. It is also possible that left == len(sigma_bounds)
    # therefore we should return sigma_bounds[right] to avoid out of bounds errors.
    return sigma_bounds[right]
