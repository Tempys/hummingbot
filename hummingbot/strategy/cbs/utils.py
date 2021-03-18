from decimal import Decimal
from typing import List
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from .data_types import CbsProposal, CbsProposalSide


# Now how do you check that top-level function are separated by 2 blank lines?
async def create_cbs_proposals(market_info_1: MarketTradingPairTuple,
                               order_amount: Decimal,is_previous_side_trade_buy) -> List[CbsProposal]:
    order_amount = Decimal(str(order_amount))
    results = []
    is_buy = False if is_previous_side_trade_buy else True # bool(0) is False, so start with buy first
    m_1_q_price = await market_info_1.market.get_quote_price(market_info_1.trading_pair, is_buy, order_amount)
    m_1_o_price = await market_info_1.market.get_order_price(market_info_1.trading_pair, is_buy, order_amount)
    # think what to do with this lline if any(p is None for p in (m_1_o_price, m_1_q_price)): continue
    first_side = CbsProposalSide(market_info_1, is_buy, m_1_q_price, m_1_o_price, order_amount)
    results.append(CbsProposal(first_side))

    return results
