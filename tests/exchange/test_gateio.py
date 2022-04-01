from unittest.mock import MagicMock

import pytest

from freqtrade.exceptions import OperationalException
from freqtrade.exchange import Gateio
from freqtrade.resolvers.exchange_resolver import ExchangeResolver
from tests.conftest import get_mock_coro, get_patched_exchange


pytestmark = pytest.mark.asyncio


async def test_validate_order_types_gateio(default_conf, mocker):
    default_conf['exchange']['name'] = 'gateio'
    mocker.patch('freqtrade.exchange.Exchange._init_ccxt')
    mocker.patch('freqtrade.exchange.Exchange.load_markets', get_mock_coro({}))
    mocker.patch('freqtrade.exchange.Exchange.validate_pairs')
    mocker.patch('freqtrade.exchange.Exchange.validate_timeframes')
    mocker.patch('freqtrade.exchange.Exchange.validate_stakecurrency')
    mocker.patch('freqtrade.exchange.Exchange.name', 'Gateio')
    exch = await ExchangeResolver.load_exchange('gateio', default_conf, load_markets=True)
    assert isinstance(exch, Gateio)

    default_conf['order_types'] = {
        'buy': 'market',
        'sell': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }

    with pytest.raises(OperationalException,
                       match=r'Exchange .* does not support market orders.'):
        await ExchangeResolver.load_exchange('gateio', default_conf, load_markets=True)


async def test_fetch_stoploss_order_gateio(default_conf, mocker):
    exchange = await get_patched_exchange(mocker, default_conf, id='gateio')

    fetch_order_mock = get_mock_coro()
    exchange.fetch_order = fetch_order_mock

    await exchange.fetch_stoploss_order('1234', 'ETH/BTC')
    assert fetch_order_mock.call_count == 1
    assert fetch_order_mock.call_args_list[0][1]['order_id'] == '1234'
    assert fetch_order_mock.call_args_list[0][1]['pair'] == 'ETH/BTC'
    assert fetch_order_mock.call_args_list[0][1]['params'] == {'stop': True}


async def test_cancel_stoploss_order_gateio(default_conf, mocker):
    exchange = await get_patched_exchange(mocker, default_conf, id='gateio')

    cancel_order_mock = get_mock_coro()
    exchange.cancel_order = cancel_order_mock

    await exchange.cancel_stoploss_order('1234', 'ETH/BTC')
    assert cancel_order_mock.call_count == 1
    assert cancel_order_mock.call_args_list[0][1]['order_id'] == '1234'
    assert cancel_order_mock.call_args_list[0][1]['pair'] == 'ETH/BTC'
    assert cancel_order_mock.call_args_list[0][1]['params'] == {'stop': True}


async def test_stoploss_adjust_gateio(mocker, default_conf):
    exchange = await get_patched_exchange(mocker, default_conf, id='gateio')
    order = {
        'price': 1500,
        'stopPrice': 1500,
    }
    assert exchange.stoploss_adjust(1501, order)
    assert not exchange.stoploss_adjust(1499, order)
