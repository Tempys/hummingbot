from hummingbot.client.config.config_validators import (
    validate_connector
)
from hummingbot.client.config.config_var import ConfigVar
from hummingbot.client.settings import (
    required_exchanges,
    requried_connector_trading_pairs,
    EXAMPLE_PAIRS,
)


def exchange_on_validated(value: str) -> None:
    required_exchanges.append(value)


def market_1_on_validated(value: str) -> None:
    requried_connector_trading_pairs[cbs_config_map["connector_1"].value] = [value]


def market_2_on_validated(value: str) -> None:
    requried_connector_trading_pairs[cbs_config_map["connector_2"].value] = [value]


def market_1_prompt() -> str:
    connector = cbs_config_map.get("connector_1").value
    example = EXAMPLE_PAIRS.get(connector)
    return "Enter the token trading pair you would like to trade on %s%s >>> " \
           % (connector, f" (e.g. {example})" if example else "")


def market_2_prompt() -> str:
    connector = cbs_config_map.get("connector_2").value
    example = EXAMPLE_PAIRS.get(connector)
    return "Enter the token trading pair you would like to trade on %s%s >>> " \
           % (connector, f" (e.g. {example})" if example else "")


def order_amount_prompt() -> str:
    trading_pair = cbs_config_map["market_1"].value
    base_asset, quote_asset = trading_pair.split("-")
    return f"What is the amount of {base_asset} per order? >>> "


cbs_config_map = {
    "strategy": ConfigVar(
        key="strategy",
        prompt="",
        default="cbs"),
    "connector_1": ConfigVar(
        key="connector_1",
        prompt="Enter your first connector (exchange/AMM) >>> ",
        prompt_on_new=True,
        validator=validate_connector,
        on_validated=exchange_on_validated),
    "market_1": ConfigVar(
        key="market_1",
        prompt=market_1_prompt,
        prompt_on_new=True,
        on_validated=market_1_on_validated),
    "order_amount": ConfigVar(
        key="order_amount",
        prompt=order_amount_prompt,
        type_str="decimal",
        prompt_on_new=True),
    "trade_pair": ConfigVar(
        key="trade_pair",
        prompt=order_amount_prompt,
        type_str="decimal",
        prompt_on_new=True),
}
