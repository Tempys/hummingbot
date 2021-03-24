from decimal import Decimal
import logging
import asyncio
import pandas as pd
from typing import List, Dict, Tuple, Optional
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.core.data_type.market_order import MarketOrder
from hummingbot.logger import HummingbotLogger
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.strategy_py_base import StrategyPyBase
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.client.settings import ETH_WALLET_CONNECTORS
from hummingbot.connector.connector.uniswap.uniswap_connector import UniswapConnector
from .utils import create_cbs_proposals, CbsProposal
from hummingbot.client.hummingbot_application import HummingbotApplication
from hummingbot.client.settings import CONF_FILE_PATH

import yaml
import decimal

NaN = float("nan")
s_decimal_zero = Decimal(0)
cbs_logger = None

#is_previous_side_trade_buy = True
#previuos_trade_price = decimal.Decimal('59079.27')


class CbsStrategy(StrategyPyBase):
    """
    This is a basic arbitrage strategy which can be used for most types of connectors (CEX, DEX or AMM).
    For a given order amount, the strategy checks both sides of the trade (market_1 and market_2) for arb opportunity.
    If presents, the strategy submits taker orders to both market.
    """

    #@classmethod
    #def get_previuos_trade_price(cls):
    #    global previuos_trade_price
    #    return previuos_trade_price

    #@classmethod
    #def previuos_trade_price(cls, value):
    #     global previuos_trade_price
    #     previuos_trade_price = value
    #
    # @classmethod
    # def get_previous_side_trade_buy(cls):
    #     global is_previous_side_trade_buy
    #     return is_previous_side_trade_buy
    #
    # @classmethod
    # def is_previous_side_trade_buy(cls, value):
    #     global is_previous_side_trade_buy
    #     is_previous_side_trade_buy = value

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global cbs_logger
        if cbs_logger is None:
            cbs_logger = logging.getLogger(__name__)
        return cbs_logger

    def __init__(self,
                 market_info_1: MarketTradingPairTuple,
                 order_amount: Decimal,
                 status_report_interval: float = 900,
                 is_previous_side_trade_buy: bool = True,
                 previuos_trade_price: Decimal = Decimal('0'),
                 min_buy_profitability: Decimal = Decimal('0.2'),
                 min_sell_profitability: Decimal = Decimal('0.2'),
                 ):
        """
        :param market_info_1: The first market
        :param order_amount: The order amount
        :param market_1_slippage_buffer: The buffer for which to adjust order price for higher chance of
        the order getting filled. This is quite important for AMM which transaction takes a long time where a slippage
        is acceptable rather having the transaction get rejected. The submitted order price will be adjust higher
        for buy order and lower for sell order.
        :param market_1_slippage_buffer: The slipper buffer for market_2
        """
        super().__init__()
        self._market_info_1 = market_info_1
        self._order_amount = order_amount
        self._is_previous_side_trade_buy = is_previous_side_trade_buy
        self._previuos_trade_price = previuos_trade_price
        self._min_buy_profitability = min_buy_profitability
        self._min_sell_profitability = min_sell_profitability
        self._last_no_arb_reported = 0
        self._arb_proposals = None
        self._all_markets_ready = False
        self._ev_loop = asyncio.get_event_loop()
        self._main_task = None
        self._first_order_done_event: Optional[asyncio.Event] = None
        self._first_order_succeeded: Optional[bool] = None
        self._first_order_id = None
        self._last_timestamp = 0
        self._status_report_interval = status_report_interval
        self.add_markets([market_info_1.market])
        self._uniswap = None
        self._quote_eth_rate_fetch_loop_task = None
        self._market_1_quote_eth_rate = None
        self._sleep_timeout = 30
        self._previous_profitability = 0

    @property
    def order_amount(self) -> Decimal:
        return self._order_amount

    @order_amount.setter
    def order_amount(self, value):
        self._order_amount = value

    # @property
    # def is_previous_side_trade_buy(self) -> bool:
    #     return self._is_previous_side_trade_buy
    #
    # @is_previous_side_trade_buy.setter
    # def is_previous_side_trade_buy(self, value):
    #     self._is_previous_side_trade_buy = value
    #
    # @property
    # def previuos_trade_price(self) -> Decimal:
    #     return self._previuos_trade_price
    #
    # @previuos_trade_price.setter
    # def previuos_trade_price(self, value):
    #     self._previuos_trade_price = value

    @property
    def market_info_to_active_orders(self) -> Dict[MarketTradingPairTuple, List[LimitOrder]]:
        return self._sb_order_tracker.market_pair_to_active_orders

    def ready_for_new_cbs_trades(self) -> bool:
        """
        Returns True if there is no outstanding unfilled order.
        """
        # outstanding_orders = self.market_info_to_active_orders.get(self._market_info, [])
        for market_info in [self._market_info_1]:
            if len(self.market_info_to_active_orders.get(market_info, [])) > 0:
                return False
        return True

    def set_price_in_file(self,price, isbuy):
        hb = HummingbotApplication.main_application()
        file_name = CONF_FILE_PATH + hb.strategy_file_name
        with open(file_name) as f:
            doc = yaml.safe_load(f)
        doc['previuos_trade_price'] = float(price)
        doc['is_previous_side_trade_buy'] = isbuy
        with open(file_name, 'w') as f:
            yaml.safe_dump(doc, f, default_flow_style=False)

    def tick(self, timestamp: float):
        """
        Clock tick entry point, is run every second (on normal tick setting).
        :param timestamp: current tick timestamp
        """
        if not self._all_markets_ready:
            self._all_markets_ready = all([market.ready for market in self.active_markets])
            if not self._all_markets_ready:
                self.logger().warning("Markets are not ready. Please wait...")
                return
            else:
                self.logger().info("Markets are ready. Trading started.")
        if self.ready_for_new_cbs_trades():
            if self._main_task is None or self._main_task.done():
                self._main_task = safe_ensure_future(self.main())

    async def main(self):
        """
        The main procedure for the cbs strategy. It first creates arbitrage proposals, then finally execute the
        arbitrage.
        """
        self.cbs_proposals = await create_cbs_proposals(self._market_info_1, self._order_amount,
                                                        self._is_previous_side_trade_buy)

        self.apply_slippage_buffers(self.cbs_proposals)
        # self.apply_budget_constraint(self.cbs_proposals)


        await self.execute_arb_proposals(self.cbs_proposals)
        await asyncio.sleep(self._sleep_timeout)

    def apply_budget_constraint(self, arb_proposals: List[CbsProposal]):
        """
        Updates arb_proposals by setting proposal amount to 0 if there is not enough balance to submit order with
        required order amount.
        :param arb_proposals: the arbitrage proposal
        """
        for arb_proposal in arb_proposals:

            for arb_side in (arb_proposal.first_side,):
                market = arb_side.market_info.market
                token = arb_side.market_info.quote_asset if arb_side.is_buy else arb_side.market_info.base_asset
                balance = market.get_available_balance(token)
                required = arb_side.amount * arb_side.order_price if arb_side.is_buy else arb_side.amount
                if balance < required:
                    arb_side.amount = s_decimal_zero
                    self.logger().info(f"Can't arbitrage, {market.display_name} "
                                       f"{token} balance "
                                       f"({balance}) is below required order amount ({required}).")
                    continue

    def apply_slippage_buffers(self, arb_proposals: List[CbsProposal]):
        """
        Updates arb_proposals by adjusting order price for slipper buffer percentage.
        E.g. if it is a buy order, for an order price of 100 and 1% slipper buffer, the new order price is 101,
        for a sell order, the new order price is 99.
        :param arb_proposals: the arbitrage proposal
        """
        for arb_proposal in arb_proposals:
            for arb_side in (arb_proposal.first_side,):
                market = arb_side.market_info.market
                arb_side.amount = market.quantize_order_amount(arb_side.market_info.trading_pair, arb_side.amount)
                arb_side.order_price = market.quantize_order_price(arb_side.market_info.trading_pair,
                                                                   arb_side.order_price)

    def profit_pct(self, previousPrice, currentprice, is_previous_side_trade_buy):
        if previousPrice == 0: return 100
        return (currentprice / previousPrice * 100 - 100) if is_previous_side_trade_buy else (
                previousPrice / currentprice * 100 - 100)

    def trade_on_exchange(self, place_order_fn, arb_side):
        self.log_with_clock(logging.INFO,
                            f"Logging order for {arb_side.amount} {arb_side.market_info.base_asset} "
                            f"at {arb_side.market_info.market.display_name} at {arb_side.order_price} price")
        order_id = place_order_fn(arb_side.market_info,
                                  arb_side.amount,
                                  arb_side.market_info.market.get_taker_order_type(),
                                  arb_side.order_price,
                                  )
        self._first_order_id = order_id
        self._first_order_done_event = asyncio.Event()

    def is_grow_profit(self,current_profitability,previous_profitablity):
        if previous_profitablity > current_profitability:
           self._previous_profitability= current_profitability
           self._sleep_timeout = 30
           self.logger().info(f"current Profitablity decrease by { current_profitability - previous_profitablity}")
           return False
        else:
           self._sleep_timeout = 5
           self._previous_profitability= current_profitability
           self.logger().info(f"current Profitablity encrease by {current_profitability - previous_profitablity}")
           return True

    async def execute_arb_proposals(self, arb_proposals: List[CbsProposal]):
        """
        Execute both sides of the arbitrage trades. If concurrent_orders_submission is False, it will wait for the
        first order to fill before submit the second order.
        :param arb_proposals: the arbitrage proposal
        """
        for arb_proposal in arb_proposals:
            if any(p.amount <= s_decimal_zero for p in (arb_proposal.first_side,)):
                continue
            self.logger().info(f"Found arbitrage opportunity!: {arb_proposal}")
            for arb_side in (arb_proposal.first_side,):
                if (self._first_order_done_event is not None):
                    await self._first_order_done_event.wait()
                    if not self._first_order_succeeded:
                        self._first_order_succeeded = None
                        continue

                prev_price = self._previuos_trade_price
                profitability = self.profit_pct(prev_price, arb_side.order_price, self._is_previous_side_trade_buy)
                if self.is_grow_profit(profitability, self._previous_profitability): continue
                self.logger().info(f"for amount: {arb_side.amount} and price {arb_side.order_price} calculates possible profitabity: {profitability} % ,  (side is buy : {arb_side.is_buy} ), previous side trade: {self._is_previous_side_trade_buy}, ")
                if arb_side.is_buy is not True and arb_side.order_price > 0.17 and self._is_previous_side_trade_buy and profitability > self._min_sell_profitability:
                    self.logger().info(f"start sell tokens")
                    place_order_fn = self.sell_with_specific_market
                    self.log_with_clock(logging.INFO,
                                        f"Logging order for {arb_side.amount} {arb_side.market_info.base_asset} "
                                        f"at {arb_side.market_info.market.display_name} at {arb_side.order_price} price")
                    order_id = place_order_fn(arb_side.market_info,
                                              arb_side.amount,
                                              arb_side.market_info.market.get_taker_order_type(),
                                              arb_side.order_price,
                                              )
                    self._first_order_id = order_id
                    self._is_previous_side_trade_buy = False
                    self._previuos_trade_price = arb_side.order_price
                    self._previous_profitability = 0
                    self.set_price_in_file(self._previuos_trade_price, self._is_previous_side_trade_buy)
                    self._first_order_done_event = asyncio.Event()
                    self.logger().info(
                        f"finish sell tokens with the profitability in {profitability} amount {arb_side.amount / 100 * profitability} rose")
                elif arb_side.is_buy is True and self._is_previous_side_trade_buy is not True and profitability > self._min_buy_profitability:
                    self.logger().info(f"start buy tokens")
                    place_order_fn = self.buy_with_specific_market
                    self.log_with_clock(logging.INFO,
                                        f"Logging order for {arb_side.amount} {arb_side.market_info.base_asset} "
                                        f"at {arb_side.market_info.market.display_name} at {arb_side.order_price} price")
                    order_id = place_order_fn(arb_side.market_info,
                                              (arb_side.amount*Decimal('1.002')),
                                              arb_side.market_info.market.get_taker_order_type(),
                                              arb_side.order_price,
                                              )
                    self._first_order_id = order_id
                    self._is_previous_side_trade_buy = True
                    self._previuos_trade_price = arb_side.order_price
                    self._previous_profitability = 0
                    self.set_price_in_file(self._previuos_trade_price, self._is_previous_side_trade_buy)
                    self._first_order_done_event = asyncio.Event()
                    self.logger().info(
                        f"finish buy tokens with the profitability in {profitability} amount {arb_side.amount / 100 * profitability} rose")

    def ready_for_new_arb_trades(self) -> bool:
        """
        Returns True if there is no outstanding unfilled order.
        """
        # outstanding_orders = self.market_info_to_active_orders.get(self._market_info, [])
        for market_info in [self._market_info_1, self._market_info_2]:
            if len(self.market_info_to_active_orders.get(market_info, [])) > 0:
                return False
        return True

    async def format_status(self) -> str:
        """
        Returns a status string formatted to display nicely on terminal. The strings composes of 4 parts: markets,
        assets, profitability and warnings(if any).
        """

        if self._arb_proposals is None:
            return "  The strategy is not ready, please try again later."
        # active_orders = self.market_info_to_active_orders.get(self._market_info, [])
        columns = ["Exchange", "Market", "Sell Price", "Buy Price", "Mid Price"]
        data = []
        for market_info in [self._market_info_1, self._market_info_2]:
            market, trading_pair, base_asset, quote_asset = market_info
            buy_price = await market.get_quote_price(trading_pair, True, self._order_amount)
            sell_price = await market.get_quote_price(trading_pair, False, self._order_amount)
            mid_price = (buy_price + sell_price) / 2
            data.append([
                market.display_name,
                trading_pair,
                float(sell_price),
                float(buy_price),
                float(mid_price)
            ])
        markets_df = pd.DataFrame(data=data, columns=columns)
        lines = []
        lines.extend(["", "  Markets:"] + ["    " + line for line in markets_df.to_string(index=False).split("\n")])

        assets_df = self.wallet_balance_data_frame([self._market_info_1, self._market_info_2])
        lines.extend(["", "  Assets:"] +
                     ["    " + line for line in str(assets_df).split("\n")])

        lines.extend(["", "  Profitability:"] + self.short_proposal_msg(self._arb_proposals))

        warning_lines = self.network_warning([self._market_info_1])
        warning_lines.extend(self.network_warning([self._market_info_2]))
        warning_lines.extend(self.balance_warning([self._market_info_1]))
        warning_lines.extend(self.balance_warning([self._market_info_2]))
        if len(warning_lines) > 0:
            lines.extend(["", "*** WARNINGS ***"] + warning_lines)

        return "\n".join(lines)

    def did_complete_buy_order(self, order_completed_event):
        self.first_order_done(order_completed_event, True)

    def did_complete_sell_order(self, order_completed_event):
        self.first_order_done(order_completed_event, True)

    def did_fail_order(self, order_failed_event):
        self.first_order_done(order_failed_event, False)

    def did_cancel_order(self, cancelled_event):
        self.first_order_done(cancelled_event, True)

    def did_expire_order(self, expired_event):
        self.first_order_done(expired_event, True)

    def first_order_done(self, event, succeeded):
        if self._first_order_done_event is not None and event.order_id == self._first_order_id:
            self._first_order_done_event.set()
            self._first_order_succeeded = succeeded

    @property
    def tracked_limit_orders(self) -> List[Tuple[ConnectorBase, LimitOrder]]:
        return self._sb_order_tracker.tracked_limit_orders

    @property
    def tracked_market_orders(self) -> List[Tuple[ConnectorBase, MarketOrder]]:
        return self._sb_order_tracker.tracked_market_orders

    def start(self, clock: Clock, timestamp: float):
        if self._market_info_1.market.name in ETH_WALLET_CONNECTORS:
            self._quote_eth_rate_fetch_loop_task = safe_ensure_future(self.quote_in_eth_rate_fetch_loop())

    def stop(self, clock: Clock):
        if self._quote_eth_rate_fetch_loop_task is not None:
            self._quote_eth_rate_fetch_loop_task.cancel()
            self._quote_eth_rate_fetch_loop_task = None
        if self._main_task is not None:
            self._main_task.cancel()
            self._main_task = None

    async def quote_in_eth_rate_fetch_loop(self):
        while True:
            try:
                if self._market_info_1.market.name in ETH_WALLET_CONNECTORS and \
                        "WETH" not in self._market_info_1.trading_pair.split("-"):
                    self._market_1_quote_eth_rate = await self.request_rate_in_eth(self._market_info_1.quote_asset)
                    self.logger().warning(f"Estimate conversion rate - "
                                          f"{self._market_info_1.quote_asset}:ETH = {self._market_1_quote_eth_rate} ")

                if self._market_info_2.market.name in ETH_WALLET_CONNECTORS and \
                        "WETH" not in self._market_info_2.trading_pair.split("-"):
                    self._market_2_quote_eth_rate = await self.request_rate_in_eth(self._market_info_2.quote_asset)
                    self.logger().warning(f"Estimate conversion rate - "
                                          f"{self._market_info_2.quote_asset}:ETH = {self._market_2_quote_eth_rate} ")
                await asyncio.sleep(60 * 5)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.logger().error(str(e), exc_info=True)
                self.logger().network("Unexpected error while fetching ETH conversion rate.",
                                      exc_info=True,
                                      app_warning_msg="Could not fetch ETH conversion rate from Gateway API.")
                await asyncio.sleep(0.5)

    async def request_rate_in_eth(self, quote: str) -> int:
        if self._uniswap is None:
            self._uniswap = UniswapConnector([f"{quote}-WETH"], "", None)
        return await self._uniswap.get_quote_price(f"{quote}-WETH", True, 1)
