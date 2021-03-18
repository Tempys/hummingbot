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


if __name__ == '__main__':
    pr = 0.18715
    cur = 0.18606

    test(True)

    #print(profit_pct(pr, cur, False))
