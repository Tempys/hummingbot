from decimal import Decimal
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.core.utils.estimate_fee import estimate_fee

s_decimal_nan = Decimal("NaN")
s_decimal_0 = Decimal("0")


class CbsProposalSide:
    """
        An  proposal side which contains info needed for order submission.
        """
    def __init__(self,
                 market_info: MarketTradingPairTuple,
                 is_buy: bool,
                 quote_price: Decimal,
                 order_price: Decimal,
                 amount: Decimal
                 ):
        """
                :param market_info: The market where to submit the order
                :param is_buy: True if buy order
                :param quote_price: The quote price (for an order amount) from the market
                :param order_price: The price required for order submission, this could differ from the quote price
                :param amount: The order amount
                """
        self.market_info: MarketTradingPairTuple = market_info
        self.is_buy: bool = is_buy
        self.quote_price: Decimal = quote_price
        self.order_price: Decimal = order_price
        self.amount: Decimal = amount

    def __repr__(self):
        side = "buy" if self.is_buy else "sell"
        return f"Connector: {self.market_info.market.display_name}  Side: {side}  Quote Price: {self.quote_price}  " \
               f"Order Price: {self.order_price}  Amount: {self.amount}"



class CbsProposal:
    """
    An arbitrage proposal which contains 2 sides of the proposal - one buy and one sell.
    """
    def __init__(self, first_side: CbsProposalSide, second_side: CbsProposalSide):
        if first_side.is_buy == second_side.is_buy:
            raise Exception("first_side and second_side must be on different side of buy and sell.")
        self.first_side: CbsProposalSide = first_side
        self.second_side: CbsProposalSide = second_side
