
def profit_pct(previousPrice, currentprice, is_previous_side_trade_buy):
    if previousPrice == 0: return 100
    return (currentprice / previousPrice * 100 - 100) if is_previous_side_trade_buy else \
                (previousPrice / currentprice * 100 - 100)



if __name__ == '__main__':
        pr =  0.21193465
        cur = 0.2

        print(profit_pct(pr,cur,True))