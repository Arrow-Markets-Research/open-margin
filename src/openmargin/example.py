import random
import datetime
import pandas as pd

from openmargin.risk import RiskConfig, PricePathGenerator, VAR, RiskModel, RiskCalc
from openmargin.auxiliary import get_underlier_price, deribit_option_data

################################################################
# Locked Margin Calculator
################################################################
ticker = "eth"

expiration = datetime.datetime.strptime('2024-09-27 08:00:00', "%Y-%m-%d %H:%M:%S")
strike = 7000.0
kind = "C"
position = -1
portfolio = {'expiration': expiration, 'strike': strike, 'kind': kind, 'position': position}
portfolio = pd.DataFrame([portfolio],columns = ["expiration", "strike", "kind", "position"])

risk_calculator = RiskCalc(ticker = ticker, portfolio = portfolio)
print(risk_calculator.get_margin())

#? Custom Inputs
################################################################
# Risk Parameters
################################################################
r = 0.05
sampling_frequency = 1 # hours
steps = 24

risk_params = RiskConfig(r, sampling_frequency, steps)

################################################################
# Price Paths
################################################################
ticker = "eth"
spot = get_underlier_price(ticker)
number_of_paths = 1_000

price_paths = PricePathGenerator(ticker = ticker, risk_params = risk_params, spot = spot, number_of_paths = number_of_paths)

sample_paths = price_paths.generate_paths()

################################################################
# Options Data
################################################################
utcnow = datetime.datetime.now(tz=datetime.timezone.utc)
(expiration_datetimes, yearly_times_to_expiration, strikes, log_moneynesses, contract_types, spot_prices, yearly_mark_implied_volatilities, mark_prices, prices) = deribit_option_data(ticker, utcnow)
options_data = pd.DataFrame([spot_prices, expiration_datetimes, yearly_times_to_expiration, strikes, log_moneynesses, contract_types, yearly_mark_implied_volatilities, mark_prices, prices]).T
options_data.columns = ['spot', 'expiration','tte','strike', 'log_money', 'kind','mark_iv','mark_price', 'price']
options_data = options_data.reset_index(drop=True)

options_data.to_csv(f'risk/options_data.csv', index = False)
# options_data = pd.read_csv(f'risk/options_data.csv', parse_dates=['expiration'])

################################################################
# Portfolio
################################################################
number_of_instruments = 1
quantities = random.choices([-1, 1], k = number_of_instruments)
portfolio = options_data.sample(n = number_of_instruments)
portfolio['position'] = quantities
portfolio = portfolio.drop(columns=['spot', 'tte', 'log_money', 'mark_iv', 'mark_price', 'price']).reset_index(drop=True)

################################################################
# Risk Model
################################################################
var_type = 'CVAR'
var_threshold = 0.01
margin_method = VAR(var_type, var_threshold)

risk_model = RiskModel(margin_method)

################################################################
# Margin Calculator
################################################################
risk_calculator = RiskCalc(ticker, portfolio, options_data, risk_params, risk_model, price_paths)
print(risk_calculator.get_margin())
