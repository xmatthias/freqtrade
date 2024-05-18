import logging
from typing import Any, Dict

import rapidjson

from freqtrade.configuration import setup_utils_configuration
from freqtrade.enums import RunMode
from freqtrade.resolvers import ExchangeResolver


logger = logging.getLogger(__name__)


async def start_test_pairlist(args: Dict[str, Any]) -> None:
    """
    Test Pairlist configuration
    """
    from freqtrade.persistence import FtNoDBContext
    from freqtrade.plugins.pairlistmanager import PairListManager

    config = setup_utils_configuration(args, RunMode.UTIL_EXCHANGE)

    exchange = await ExchangeResolver.load_exchange(config, load_markets=False, validate=False)

    quote_currencies = args.get("quote_currencies")
    if not quote_currencies:
        quote_currencies = [config.get("stake_currency")]
    results = {}
    with FtNoDBContext():
        for curr in quote_currencies:
            config["stake_currency"] = curr
            pairlists = PairListManager(exchange, config)
            await pairlists.refresh_pairlist()
            results[curr] = pairlists.whitelist

    for curr, pairlist in results.items():
        if not args.get("print_one_column", False) and not args.get("list_pairs_print_json", False):
            print(f"Pairs for {curr}: ")

        if args.get("print_one_column", False):
            print("\n".join(pairlist))
        elif args.get("list_pairs_print_json", False):
            print(rapidjson.dumps(list(pairlist), default=str))
        else:
            print(pairlist)
