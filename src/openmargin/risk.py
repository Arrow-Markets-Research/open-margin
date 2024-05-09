import numpy as np
import pandas as pd
import datetime

import warnings
warnings.filterwarnings('ignore')

from openmargin.auxiliary import *

class RiskConfig:
    def __init__(self,
                 r = 0.05,
                 sampling_frequency = 1, 
                 steps = 24,
                 **kwargs):
        
        self.r = r # continuously compounded interest rate
        self.sampling_frequency = sampling_frequency # empirical sample generation & mjd option prices
        self.steps = steps
        self.trading_horizon = sampling_frequency * steps # empirical sample generation, option pricing
        self.T = self.trading_horizon / hours_per_year # Trading Horizon
        self.dt = self.sampling_frequency / hours_per_year
        self.kwargs = kwargs

class PricePathGenerator:
    def __init__(self, 
                 ticker: str,
                 risk_params: RiskConfig,
                 spot = None,
                 number_of_paths = 1_000,
                 historical_prices = None):

        self.ticker = ticker
        self.risk_params = risk_params
    
        if spot is None:
            self.spot = get_underlier_price(ticker)
        else:
            self.spot = spot
        
        self.number_of_paths = number_of_paths
        self.historical_prices = historical_prices

    def generate_paths(self):
        self.sample_paths = pd.DataFrame(index=range(self.risk_params.steps),columns=range(self.number_of_paths))
        
        if self.historical_prices is None:
            self.historical_prices = get_historical_prices(Ticker.cast(self.ticker), self.risk_params.sampling_frequency)

        historical_returns = np.diff(np.log(self.historical_prices))

        for i in range(self.number_of_paths):
            bootstrap = pd.DataFrame(historical_returns).sample(n = self.risk_params.steps, replace = True)[0].values.tolist()
            cum_ret = cumsum_list(bootstrap)
            path = np.exp(np.array(cum_ret)) * self.spot
            self.sample_paths.iloc[:,i] = path

        return self.sample_paths

class VAR:
    def __init__(self,
                 var_type = 'CVAR',
                 var_threshold = 0.01):
        
        self.var_type = var_type
        self.var_threshold = var_threshold

class RiskModel:
    def __init__(self,
                 margin_method: VAR):
        
        self.margin_method = margin_method

class RiskCalc:
    def __init__(self,
                 ticker: str,
                 portfolio: pd.DataFrame, # Portfolio
                 options_data = None, # OptionData
                 risk_params = None, # RiskConfig
                 risk_model = None, # RiskModel
                 price_paths = None): # PricePathGenerator
        
        self.ticker = ticker
        self.portfolio = portfolio
        self.options_data = options_data
        self.risk_params = risk_params
        self.risk_model = risk_model
        self.price_paths = price_paths

        self.input_check = True
        allowed_tickers = ['btc', 'eth']

        # Ticker Checks
        if type(ticker) != str:
            self.input_check = False
            print("Ticker needs to be a string input e.g. 'btc'")
        else:
            if ticker not in allowed_tickers:
                self.input_check = False
                print("Ticker not allowed!")
        
        # Portfolio Checks
        if type(portfolio) != pd.DataFrame:
            self.input_check = False
            print("Portfolio needs to be a DataFrame")

        if pd.Series(["expiration", "strike", "kind", "position"]).isin(portfolio.columns).all() == False:
            self.input_check = False
            print("Portfolio needs to be a DataFrame with the following columns: expiration, strike, kind, position")

        date_format = '%Y-%m-%d %H:%M:%S'
        
        #? expiration
        try:
            for port_date in portfolio.expiration:
                date_obj = port_date.strftime(date_format)                
        except:
            print("Incompatible expiration string format, date string needs to be of the form: '%Y-%m-%d %H:%M:%S'")

        #? strike
        for strike in portfolio.strike:
            if type(strike) == float:
                continue
            elif type(strike) == np.float_:
                continue
            else:
                # self.input_check = False
                print("Option strikes need to be a vector of floats, e.g 2000.0")

        #?kind
        allowed_option_types = ['C', 'P']
        for kind in portfolio.kind:
            if type(kind) == str:
                continue
            elif type(kind) == np.str_:
                continue    
            elif kind.upper() not in allowed_option_types:
                self.input_check = False
                print("Option kind needs to be a string; C and P for call and put options respectively.")
                break
            else:
                self.input_check = False
                print("Option kind needs to be a string; C and P for call and put options respectively.")
                break
        
        #? position
        for position in portfolio.position:
            if type(position) == int:
                continue
            elif type(position) == np.int_:
                continue
            else:
                self.input_check = False
                print("Option positions need to be a vector of floats, e.g 1.0")
                break
        
        if self.input_check:
            if self.options_data is None:
                self.utcnow = datetime.datetime.now(tz=datetime.timezone.utc)
                spot = get_underlier_price(ticker)
                (expiration_datetimes, yearly_times_to_expiration, strikes, log_moneynesses, contract_types, spot_prices, yearly_mark_implied_volatilities, mark_prices, prices) = deribit_option_data(ticker, self.utcnow)
                options_data = pd.DataFrame([spot_prices, expiration_datetimes, yearly_times_to_expiration, strikes, log_moneynesses, contract_types, yearly_mark_implied_volatilities, mark_prices, prices]).T
                options_data.columns = ['spot', 'expiration','tte','strike', 'log_money', 'kind','mark_iv','mark_price', 'price']
                options_data = options_data.reset_index(drop=True)
                options_data['spot'] = spot
                options_data['log_money'] = np.log(options_data['strike'].astype(float) / spot)
                self.options_data = options_data

            self.options_data = self.options_data[self.options_data.expiration.isin(portfolio.expiration.unique())].reset_index(drop=True)

            portfolio_indices = self.index_finder(portfolio)

            if len(portfolio_indices) < len(portfolio):
                print("Portfolio contains unidentified assets, cannot continue!")
                self.input_check = False
            else:
                positions = portfolio.position.tolist()
                self.portfolio = self.options_data.loc[portfolio_indices]
                self.portfolio['position'] = positions
        
        if self.input_check:
            if self.risk_params is None:
                self.risk_params = RiskConfig()
            else:
                self.risk_params = risk_params

            if self.risk_model is None:
                self.risk_model = RiskModel(VAR())
            else:
                self.risk_model = risk_model

            if self.price_paths is None:
                self.price_paths = PricePathGenerator(ticker = self.ticker, risk_params = self.risk_params, spot = spot)
            else:
                self.price_paths = price_paths

    def index_finder(self, portfolio):
        if self.input_check == True:
            portfolio_indices = []
            for i in range(len(portfolio)):
                option = portfolio.iloc[i]            
                expiration = option.expiration
                strike = option.strike
                kind = option.kind
                idx = self.options_data[(self.options_data.expiration == expiration) & (self.options_data.strike == strike) & (self.options_data.kind == kind)].index.to_list()[0]
                portfolio_indices.append(idx)
        else:
            portfolio_indices = []
        return portfolio_indices

    def get_margin(self):
        try:
            if self.input_check:
                ###################################################################
                # VAR - CVAR
                ###################################################################
                if type(self.risk_model.margin_method) == VAR:
                    sample_paths = self.price_paths.generate_paths()
                    row, col = sample_paths.shape
                    option_VaR = []

                    for idx in self.portfolio.index.to_list():
                        option = self.portfolio.loc[idx]
                        option_price = option['price']
                        strike = option['strike']
                        kind = option['kind']
                        tte = option['tte']
                        
                        path_option_pnl = []

                        for i in range(0, col): 
                            option_pnl = []

                            _spot = self.price_paths.spot

                            for j in range(self.risk_params.sampling_frequency - 1, self.risk_params.trading_horizon, self.risk_params.sampling_frequency):
                                _spot = sample_paths.iloc[(j + 1) // self.risk_params.sampling_frequency - 1, i]

                                tte = max(option['tte'] - ((j + 1) * self.risk_params.sampling_frequency / hours_per_year), 0)

                                if tte > 0:
                                    if kind == 'C':
                                            bsm_vol = option.mark_iv
                                            new_option_price = bs_call(_spot, strike, tte, self.risk_params.r, bsm_vol)
                                    elif kind == 'P':
                                            bsm_vol = option.mark_iv
                                            new_option_price = bs_put(_spot, strike, tte, self.risk_params.r, bsm_vol)
                                    else:
                                        new_option_price = 0
                                else:
                                    new_option_price = 0

                                _option_pnl = new_option_price - option_price
                                option_pnl.append(_option_pnl)
                                    
                            path_option_pnl.append(option_pnl)

                        option_VaR.append(path_option_pnl)
                    
                    self.portfolio['option_VaR'] = option_VaR

                    #########################################################
                    # VAR-CVAR Calculation
                    #########################################################
                    portfolio_pnls = []
                    portfolio_pnl_paths = []

                    for i in range(self.price_paths.number_of_paths):
                        option_pnls = []
                        for idx in self.portfolio.index.values.tolist():
                            _nom_VaR = np.array(self.portfolio.loc[idx, 'option_VaR'][i]) * self.portfolio.loc[idx, 'position']
                            option_pnls.append(_nom_VaR)

                        portfolio_pnls.append(min(sum(option_pnls)))
                        portfolio_pnl_paths.append(sum(option_pnls))

                    sorted_portfolio_pnls = np.sort(np.round(portfolio_pnls, 2)).tolist()
                    mc_VaR = np.percentile(sorted_portfolio_pnls, self.risk_model.margin_method.var_threshold * 100, method = "closest_observation")

                    if self.risk_model.margin_method.var_type.lower() == 'var':
                        self.margin = np.round(mc_VaR, 2)
                        self.successful_completion = True
                    elif self.risk_model.margin_method.var_type.lower() == 'cvar':
                        VaR_loc = np.where(sorted_portfolio_pnls == mc_VaR)[0].tolist()[0]
                        mc_cVaR = np.average(sorted_portfolio_pnls[0:VaR_loc+1])
                        self.margin = np.round(mc_cVaR, 2)
                        self.successful_completion = True
                    else:
                        print("VAR or CVAR methods allowed only!")
                        self.margin = 0
                        self.successful_completion = False
                else:
                    print("Unknown Margining Method!")
                    self.margin = 0
                    self.successful_completion = False
            
                return [self.margin, self.successful_completion]

            else: # Failed input check
                print('Input Check Failure')
                self.margin = 0
                self.successful_completion = self.input_check
                return [self.margin, self.successful_completion]
            
        except: # General Error
            print('Unknown Error')
            self.margin = 0
            self.successful_completion = False
            return [self.margin, self.successful_completion]
