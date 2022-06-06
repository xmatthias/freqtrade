import logging
import time
from unittest.mock import MagicMock, PropertyMock

import pytest

from freqtrade.data.dataprovider import DataProvider
from freqtrade.enums import State
from tests.conftest import get_mock_coro, get_patched_worker, log_has, log_has_re


pytestmark = pytest.mark.asyncio


async def test_worker_state(mocker, default_conf, markets) -> None:
    mocker.patch('freqtrade.exchange.Exchange.markets', PropertyMock(return_value=markets))
    worker = await get_patched_worker(mocker, default_conf)
    assert worker.freqtrade.state is State.RUNNING

    default_conf.pop('initial_state')
    worker = await get_patched_worker(mocker, default_conf)
    assert worker.freqtrade.state is State.STOPPED


async def test_worker_running(mocker, default_conf, caplog) -> None:
    mock_throttle = get_mock_coro()
    mocker.patch('freqtrade.worker.Worker._throttle', mock_throttle)
    mocker.patch('freqtrade.persistence.Trade.stoploss_reinitialization', MagicMock())

    worker = await get_patched_worker(mocker, default_conf)

    state = await worker._worker(old_state=None)
    assert state is State.RUNNING
    assert log_has('Changing state to: RUNNING', caplog)
    assert mock_throttle.call_count == 1
    # Check strategy is loaded, and received a dataprovider object
    assert worker.freqtrade.strategy
    assert worker.freqtrade.strategy.dp
    assert isinstance(worker.freqtrade.strategy.dp, DataProvider)


async def test_worker_stopped(mocker, default_conf, caplog) -> None:
    mock_throttle = get_mock_coro()
    mocker.patch('freqtrade.worker.Worker._throttle', mock_throttle)

    worker = await get_patched_worker(mocker, default_conf)
    worker.freqtrade.state = State.STOPPED
    state = await worker._worker(old_state=State.RUNNING)
    assert state is State.STOPPED
    assert log_has('Changing state from RUNNING to: STOPPED', caplog)
    assert mock_throttle.call_count == 1


async def test_throttle(mocker, default_conf, caplog) -> None:
    async def throttled_func():
        return 42

    caplog.set_level(logging.DEBUG)
    worker = await get_patched_worker(mocker, default_conf)

    start = time.time()
    result = await worker._throttle(throttled_func, throttle_secs=0.1)
    end = time.time()

    assert result == 42
    assert end - start > 0.1
    assert log_has_re(r"Throttling with 'throttled_func\(\)': sleep for \d\.\d{2} s.*", caplog)

    result = await worker._throttle(throttled_func, throttle_secs=-1)
    assert result == 42


async def test_throttle_with_assets(mocker, default_conf) -> None:
    async def throttled_func(nb_assets=-1):
        return nb_assets

    worker = await get_patched_worker(mocker, default_conf)

    result = await worker._throttle(throttled_func, throttle_secs=0.1, nb_assets=666)
    assert result == 666

    result = await worker._throttle(throttled_func, throttle_secs=0.1)
    assert result == -1


async def test_worker_heartbeat_running(default_conf, mocker, caplog):
    message = r"Bot heartbeat\. PID=.*state='RUNNING'"

    mock_throttle = get_mock_coro()
    mocker.patch('freqtrade.worker.Worker._throttle', mock_throttle)
    worker = await get_patched_worker(mocker, default_conf)

    worker.freqtrade.state = State.RUNNING
    await worker._worker(old_state=State.STOPPED)
    assert log_has_re(message, caplog)

    caplog.clear()
    # Message is not shown before interval is up
    await worker._worker(old_state=State.RUNNING)
    assert not log_has_re(message, caplog)

    caplog.clear()
    # Set clock - 70 seconds
    worker._heartbeat_msg -= 70
    await worker._worker(old_state=State.RUNNING)
    assert log_has_re(message, caplog)


async def test_worker_heartbeat_stopped(default_conf, mocker, caplog):
    message = r"Bot heartbeat\. PID=.*state='STOPPED'"

    mock_throttle = get_mock_coro()
    mocker.patch('freqtrade.worker.Worker._throttle', mock_throttle)
    worker = await get_patched_worker(mocker, default_conf)

    worker.freqtrade.state = State.STOPPED
    await worker._worker(old_state=State.RUNNING)
    assert log_has_re(message, caplog)

    caplog.clear()
    # Message is not shown before interval is up
    await worker._worker(old_state=State.STOPPED)
    assert not log_has_re(message, caplog)

    caplog.clear()
    # Set clock - 70 seconds
    worker._heartbeat_msg -= 70
    await worker._worker(old_state=State.STOPPED)
    assert log_has_re(message, caplog)
