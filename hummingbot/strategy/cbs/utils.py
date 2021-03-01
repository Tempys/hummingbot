from decimal import Decimal
from typing import List
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from .data_types import ArbProposal, ArbProposalSide






async def create_cbs_proposals(market_info_1: MarketTradingPairTuple,
                               order_amount: Decimal) -> List[ArbProposal]: