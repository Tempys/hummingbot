from hummingbot.strategy.cbs.cbs_config_map import cbs_config_map
from hummingbot.strategy.cbs.cbs import CbsStrategy
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple


def start(self):
    connector_1 = cbs_config_map.get("connector_1").value.lower()
    market_1 = cbs_config_map.get("market_1").value
    order_amount = cbs_config_map.get("order_amount").value
    is_previous_side_trade_buy = cbs_config_map.get("is_previous_side_trade_buy").value
    previuos_trade_price = cbs_config_map.get("previuos_trade_price").value
    min_buy_profitability = cbs_config_map.get("min_buy_profitability").value
    min_sell_profitability = cbs_config_map.get("min_sell_profitability").value

    self._initialize_markets([(connector_1, [market_1])])
    base_1, quote_1 = market_1.split("-")
    self.assets = set([base_1, quote_1])

    market_info_1 = MarketTradingPairTuple(self.markets[connector_1], market_1, base_1, quote_1)

    self.market_trading_pair_tuples = [market_info_1]
    self.strategy = CbsStrategy(market_info_1,
                                order_amount,
                                900,
                                is_previous_side_trade_buy,
                                previuos_trade_price,
                                min_buy_profitability,
                                min_sell_profitability
                                )
