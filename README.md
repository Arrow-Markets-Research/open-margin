<p align="center"><img width=20% src="https://github.com/Arrow-Markets-Research/openmargin/raw/main/arrow-markets.png"></p>

![Python](https://img.shields.io/badge/python-v3.8+-green.svg)
![Version](https://img.shields.io/badge/version-0.0.1-red.svg)
![License](https://img.shields.io/badge/license-GNU-blue.svg)

# Open Margin

Arrow Markets open source repository to calculate margin requirements for risky asset portfolios including crypto options portfolios.

## Overview

This repository includes a simplified version of the proprietary Arrow Markets margin calculator. It uses VAR/CVAR methodology to compute the necessary margin required for a portfolio of BTC or ETH options. <br />
Negative values refer to the cash margin needed for a given portfolio, while positive margin values count as credits. For further details, please refer to the white paper ["Automated Margin Systems in Practice"](https://drive.google.com/file/d/1y_113sCg4kOkU8lRDnyRjCovNpDMLNcM/view?usp=drive_link)

## Installation

```bash
pip install openmargin
```

## Dependencies

```bash
pip install -r requirements.txt
```
## Usage

Open Margin calculates the risk of an options portfolio through RiskCalc. <br />
Once a compatible ticker and an options portfolio are provided portfolio margin can be computed with default parameters via: <br />

```python
import datetime
import pandas as pd
from openmargin.risk import RiskCalc

ticker = "eth"

expiration = datetime.datetime.strptime('2024-09-27 08:00:00', "%Y-%m-%d %H:%M:%S")
strike = 7000.0
kind = "C"
position = -1
portfolio = {'expiration': expiration, 'strike': strike, 'kind': kind, 'position': position}
portfolio = pd.DataFrame([portfolio],columns = ["expiration", "strike", "kind", "position"])

risk_calculator = RiskCalc(ticker, portfolio)
risk_calculator.get_margin()

```

RiskCalc has four pillars that can be modified to generate the required margin.

### Options Data
Open Margin uses the current options data for BTC and ETH from Deribit. <br />
To provide a different dataset, please provide a pandas dataframe containing options data similar to the one shown below: 

<p align="left"><img src="https://github.com/Arrow-Markets-Research/openmargin/raw/main/options_data.png"></p>

```python
risk_calculator = RiskCalc(ticker, portfolio, options_data)
risk_calculator.get_margin()
```

### Risk Configuration
Three main risk factors are configured under RiskConfig. <br />
Interest rate, sampling frequency and steps are the key parameters currently allowed for user customization. <br />
Sampling frequency multiplied by steps determine the trading horizon that will be used to calculate margin values.

```python
from openmargin.risk import RiskConfig, RiskCalc

r = 0.02
sampling_frequency = 4 # hours
steps = 6
risk_params = RiskConfig(r, sampling_frequency, steps)

risk_calculator = RiskCalc(ticker, portfolio, risk_params = risk_params)
risk_calculator.get_margin()
```

### Risk Model
RiskModel class determines the margin method used.
Open Margin only allows VAR type margin methods in this public version.
To select between VAR and CVAR and to change margin threshold:

```python
from openmargin.risk import VAR, RiskModel, RiskCalc

var_type = 'VAR'
var_threshold = 0.05
margin_method = VAR(var_type, var_threshold)
risk_model = RiskModel(margin_method)

risk_calculator = RiskCalc(ticker, portfolio, risk_model = risk_model)
risk_calculator.get_margin()
```

### Price Paths
Path dependant methods like VAR/CVAR depend on future price paths. <br />
1,000 paths are generated by default by PricePathGenerator. <br />
Changes to the default number of paths can be made via:

```python
from openmargin.auxiliary import get_underlier_price
from openmargin.risk import PricePathGenerator, RiskCalc

spot = get_underlier_price(ticker)
number_of_paths = 10_000
price_paths = PricePathGenerator(ticker, risk_params, spot, number_of_paths)

risk_calculator = RiskCalc(ticker, portfolio, price_paths = price_paths)
risk_calculator.get_margin()
```

The paths can be generated with:

```python
sample_paths = price_paths.generate_paths()
```

Further customization examples can be found under example.py.
