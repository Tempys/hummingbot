from decimal import Decimal
from typing import List

from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from .data_types import CbsProposal, CbsProposalSide


async def create_cbs_proposals(market_info_1: MarketTradingPairTuple,
                               order_amount: Decimal) -> List[CbsProposal]:
    order_amount = Decimal(str(order_amount))
    results = []
    for index in range(0, 2):
        is_buy = not bool(index)  # bool(0) is False, so start with buy first
        m_1_q_price = await market_info_1.market.get_quote_price(market_info_1.trading_pair, is_buy, order_amount)
        m_1_o_price = await market_info_1.market.get_order_price(market_info_1.trading_pair, is_buy, order_amount)

        if any(p is None for p in (m_1_o_price, m_1_q_price)):
            continue
        first_side = CbsProposalSide(
            market_info_1,
            is_buy,
            m_1_q_price,
            m_1_o_price,
            order_amount
        )
        results.append(CbsProposal(first_side))

    return results
