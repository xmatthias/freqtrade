from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from freqtrade.enums import MarginMode, TradingMode
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
    mocker.patch('freqtrade.exchange.Exchange.validate_pricing')
    mocker.patch('freqtrade.exchange.Exchange.name', 'Gateio')
    exch = await ExchangeResolver.load_exchange('gateio', default_conf, load_markets=True)
    assert isinstance(exch, Gateio)

    default_conf['order_types'] = {
        'entry': 'market',
        'exit': 'limit',
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


@pytest.mark.parametrize('sl1,sl2,sl3,side', [
    (1501, 1499, 1501, "sell"),
    (1499, 1501, 1499, "buy")
])
async def test_stoploss_adjust_gateio(mocker, default_conf, sl1, sl2, sl3, side):
    exchange = await get_patched_exchange(mocker, default_conf, id='gateio')
    order = {
        'price': 1500,
        'stopPrice': 1500,
    }
    assert exchange.stoploss_adjust(sl1, order, side)
    assert not exchange.stoploss_adjust(sl2, order, side)


@pytest.mark.parametrize('takerormaker,rate,cost', [
    ('taker', 0.0005, 0.0001554325),
    ('maker', 0.0, 0.0),
])
async def test_fetch_my_trades_gateio(mocker, default_conf, takerormaker, rate, cost):
    mocker.patch('freqtrade.exchange.Exchange.exchange_has', return_value=True)
    mocker.patch('freqtrade.exchange.Exchange.fill_leverage_tiers')
    tick = {'ETH/USDT:USDT': {
        'info': {'user_id': '',
                 'taker_fee': '0.0018',
                 'maker_fee': '0.0018',
                 'gt_discount': False,
                 'gt_taker_fee': '0',
                 'gt_maker_fee': '0',
                 'loan_fee': '0.18',
                 'point_type': '1',
                 'futures_taker_fee': '0.0005',
                 'futures_maker_fee': '0'},
            'symbol': 'ETH/USDT:USDT',
            'maker': 0.0,
            'taker': 0.0005}
            }
    default_conf['dry_run'] = False
    default_conf['trading_mode'] = TradingMode.FUTURES
    default_conf['margin_mode'] = MarginMode.ISOLATED

    api_mock = MagicMock()
    api_mock.fetch_my_trades = get_mock_coro(return_value=[{
        'fee': {'cost': None},
        'price': 3108.65,
        'cost': 0.310865,
        'order': '22255',
        'takerOrMaker': takerormaker,
        'amount': 1,  # 1 contract
    }])
    exchange = await get_patched_exchange(mocker, default_conf, api_mock=api_mock, id='gateio')
    exchange._trading_fees = tick
    trades = await exchange.get_trades_for_order(
        '22255', 'ETH/USDT:USDT', datetime.now(timezone.utc))
    trade = trades[0]
    assert trade['fee']
    assert trade['fee']['rate'] == rate
    assert trade['fee']['currency'] == 'USDT'
    assert trade['fee']['cost'] == cost
