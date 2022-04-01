from random import randint
from unittest.mock import MagicMock

import ccxt
import pytest

from freqtrade.exceptions import DependencyException, InvalidOrderException, OperationalException
from tests.conftest import get_mock_coro, get_patched_exchange
from tests.exchange.test_exchange import async_ccxt_exception


pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('limitratio,expected', [
    (None, 220 * 0.99),
    (0.99, 220 * 0.99),
    (0.98, 220 * 0.98),
])
async def test_stoploss_order_huobi(default_conf, mocker, limitratio, expected):
    api_mock = MagicMock()
    order_id = 'test_prod_buy_{}'.format(randint(0, 10 ** 6))
    order_type = 'stop-limit'

    api_mock.create_order = get_mock_coro(return_value={
        'id': order_id,
        'info': {
            'foo': 'bar'
        }
    })
    default_conf['dry_run'] = False
    mocker.patch('freqtrade.exchange.Exchange.amount_to_precision', lambda s, x, y: y)
    mocker.patch('freqtrade.exchange.Exchange.price_to_precision', lambda s, x, y: y)

    exchange = await get_patched_exchange(mocker, default_conf, api_mock, 'huobi')

    with pytest.raises(OperationalException):
        order = await exchange.stoploss(pair='ETH/BTC', amount=1, stop_price=190,
                                        order_types={'stoploss_on_exchange_limit_ratio': 1.05})

    api_mock.create_order.reset_mock()
    order_types = {} if limitratio is None else {'stoploss_on_exchange_limit_ratio': limitratio}
    order = await exchange.stoploss(
        pair='ETH/BTC', amount=1, stop_price=220, order_types=order_types)

    assert 'id' in order
    assert 'info' in order
    assert order['id'] == order_id
    assert api_mock.create_order.call_args_list[0][1]['symbol'] == 'ETH/BTC'
    assert api_mock.create_order.call_args_list[0][1]['type'] == order_type
    assert api_mock.create_order.call_args_list[0][1]['side'] == 'sell'
    assert api_mock.create_order.call_args_list[0][1]['amount'] == 1
    # Price should be 1% below stopprice
    assert api_mock.create_order.call_args_list[0][1]['price'] == expected
    assert api_mock.create_order.call_args_list[0][1]['params'] == {"stopPrice": 220,
                                                                    "operator": "lte",
                                                                    }

    # test exception handling
    with pytest.raises(DependencyException):
        api_mock.create_order = get_mock_coro(side_effect=ccxt.InsufficientFunds("0 balance"))
        exchange = await get_patched_exchange(mocker, default_conf, api_mock, 'huobi')
        await exchange.stoploss(pair='ETH/BTC', amount=1, stop_price=220, order_types={})

    with pytest.raises(InvalidOrderException):
        api_mock.create_order = get_mock_coro(
            side_effect=ccxt.InvalidOrder("binance Order would trigger immediately."))
        exchange = await get_patched_exchange(mocker, default_conf, api_mock, 'binance')
        await exchange.stoploss(pair='ETH/BTC', amount=1, stop_price=220, order_types={})

    await async_ccxt_exception(mocker, default_conf, api_mock, "huobi",
                               "stoploss", "create_order", retries=1,
                               pair='ETH/BTC', amount=1, stop_price=220, order_types={})


async def test_stoploss_order_dry_run_huobi(default_conf, mocker):
    api_mock = MagicMock()
    order_type = 'stop-limit'
    default_conf['dry_run'] = True
    mocker.patch('freqtrade.exchange.Exchange.amount_to_precision', lambda s, x, y: y)
    mocker.patch('freqtrade.exchange.Exchange.price_to_precision', lambda s, x, y: y)

    exchange = await get_patched_exchange(mocker, default_conf, api_mock, 'huobi')

    with pytest.raises(OperationalException):
        order = await exchange.stoploss(pair='ETH/BTC', amount=1, stop_price=190,
                                        order_types={'stoploss_on_exchange_limit_ratio': 1.05})

    api_mock.create_order.reset_mock()

    order = await exchange.stoploss(pair='ETH/BTC', amount=1, stop_price=220, order_types={})

    assert 'id' in order
    assert 'info' in order
    assert 'type' in order

    assert order['type'] == order_type
    assert order['price'] == 220
    assert order['amount'] == 1


async def test_stoploss_adjust_huobi(mocker, default_conf):
    exchange = await get_patched_exchange(mocker, default_conf, id='huobi')
    order = {
        'type': 'stop',
        'price': 1500,
        'stopPrice': '1500',
    }
    assert exchange.stoploss_adjust(1501, order)
    assert not exchange.stoploss_adjust(1499, order)
    # Test with invalid order case
    order['type'] = 'stop_loss'
    assert not exchange.stoploss_adjust(1501, order)
