from decimal import Decimal
# from hummingbot.client.hummingbot_application import HummingbotApplication
import yaml


# import settings

def profit_pct(previousPrice, currentprice, is_previous_side_trade_buy):
    if previousPrice == 0: return 100
    return (currentprice / previousPrice * 100 - 100) if is_previous_side_trade_buy else \
        (previousPrice / currentprice * 100 - 100)


def test(v):
    for i in range(0, 2):
        if not v:
            v = None
            continue
        print(v)


def set_price_in_file(price, isbuy):
    file_name = "/home/m/Desktop/hummingbot/conf/test.yml"
    with open(file_name) as f:
        doc = yaml.safe_load(f)
    doc['previuos_trade_price'] = price
    doc['is_previous_side_trade_buy'] = isbuy
    with open(file_name, 'w') as f:
        yaml.safe_dump(doc, f, default_flow_style=False)


if __name__ == '__main__':
    cur = 0.18606
    set_price_in_file(float(Decimal('555')),False)
    # d = Decimal('100')
    # print(d* Decimal('1.001'))
    # test(True)

    # print(profit_pct(pr, cur, False))
