# crypto-trading-bot

## Setup ##

Install necessary packages, including Robin Stocks and Alpaca Trading API.



```pip3 install robin_stocks```,
```pip3 install alpaca-trade-api``` 


Robinhood is used for gathering data and Alpaca is used for placing orders. Therefore, an Alpaca brokerage account is required to use this project.

Initialize a ```secret.py``` file with variables corresponding to Robinhood login credentials and Alpaca API key/secret. See ```bot.py``` for specific variable names.

## Use ##

Run ```python3 bot.py``` to execute script.