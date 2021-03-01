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


NaN = float("nan")
s_decimal_zero = Decimal(0)
cbs_logger = None


class CbsStrategy(StrategyPyBase):
    """
    This is a basic arbitrage strategy which can be used for most types of connectors (CEX, DEX or AMM).
    For a given order amount, the strategy checks both sides of the trade (market_1 and market_2) for arb opportunity.
    If presents, the strategy submits taker orders to both market.
    """

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global cbs_logger
        if cbs_logger is None:
            cbs_logger = logging.getLogger(__name__)
        return cbs_logger

    def __init__(self,
                 market_info_1: MarketTradingPairTuple,
                 order_amount: Decimal,
                 status_report_interval: float = 900):
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

    @property
    def order_amount(self) -> Decimal:
        return self._order_amount

    @order_amount.setter
    def order_amount(self, value):
        self._order_amount = value

    @property
    def market_info_to_active_orders(self) -> Dict[MarketTradingPairTuple, List[LimitOrder]]:
        return self._sb_order_tracker.market_pair_to_active_orders

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
        self._cbs_proposals = await create_cbs_proposals(self._market_info_1, self._order_amount)
        await self.execute_arb_proposals(self._cbs_proposals)

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
                self.log_with_clock(logging.INFO,
                                    f"Logging order for {arb_side.amount} {arb_side.market_info.base_asset} "
                                    f"at {arb_side.market_info.market.display_name} at {arb_side.order_price} price")

    def ready_for_new_cbs_trades(self) -> bool:
        """
        Returns True if there is no outstanding unfilled order.
        """
        # outstanding_orders = self.market_info_to_active_orders.get(self._market_info, [])
        for market_info in [self._market_info_1]:
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
