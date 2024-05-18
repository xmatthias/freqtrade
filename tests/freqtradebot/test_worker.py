import logging
import time
from datetime import timedelta
from unittest.mock import MagicMock, PropertyMock

import pytest
import time_machine

from freqtrade.data.dataprovider import DataProvider
from freqtrade.enums import State
from freqtrade.exceptions import OperationalException
from tests.conftest import EXMS, get_mock_coro, get_patched_worker, log_has, log_has_re


async def test_worker_state(mocker, default_conf, markets) -> None:
    mocker.patch(f"{EXMS}.markets", PropertyMock(return_value=markets))
    worker = await get_patched_worker(mocker, default_conf)
    assert worker.freqtrade.state is State.RUNNING

    default_conf.pop("initial_state")
    worker = await get_patched_worker(mocker, default_conf)
    assert worker.freqtrade.state is State.STOPPED


async def test_worker_running(mocker, default_conf, caplog) -> None:
    mock_throttle = get_mock_coro()
    mocker.patch("freqtrade.worker.Worker._throttle", mock_throttle)
    mocker.patch("freqtrade.persistence.Trade.stoploss_reinitialization", MagicMock())

    worker = await get_patched_worker(mocker, default_conf)

    state = await worker._worker(old_state=None)
    assert state is State.RUNNING
    assert log_has("Changing state to: RUNNING", caplog)
    assert mock_throttle.call_count == 1
    # Check strategy is loaded, and received a dataprovider object
    assert worker.freqtrade.strategy
    assert worker.freqtrade.strategy.dp
    assert isinstance(worker.freqtrade.strategy.dp, DataProvider)


async def test_worker_stopped(mocker, default_conf, caplog) -> None:
    mock_throttle = get_mock_coro()
    mocker.patch("freqtrade.worker.Worker._throttle", mock_throttle)

    worker = await get_patched_worker(mocker, default_conf)
    worker.freqtrade.state = State.STOPPED
    state = await worker._worker(old_state=State.RUNNING)
    assert state is State.STOPPED
    assert log_has("Changing state from RUNNING to: STOPPED", caplog)
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
    assert 0.3 > end - start > 0.1
    assert log_has_re(r"Throttling with 'throttled_func\(\)': sleep for \d\.\d{2} s.*", caplog)

    result = await worker._throttle(throttled_func, throttle_secs=-1)
    assert result == 42


async def test_throttle_sleep_time(mocker, default_conf, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    worker = await get_patched_worker(mocker, default_conf)
    sleep_mock = mocker.patch("freqtrade.worker.Worker._sleep")
    with time_machine.travel("2022-09-01 05:00:00 +00:00") as t:

        async def throttled_func(x=1):
            t.shift(timedelta(seconds=x))
            return 42

        assert await worker._throttle(throttled_func, throttle_secs=5) == 42
        # This moves the clock by 1 second
        assert sleep_mock.call_count == 1
        assert 3.8 < sleep_mock.call_args[0][0] < 4.1

        sleep_mock.reset_mock()
        # This moves the clock by 1 second
        assert await worker._throttle(throttled_func, throttle_secs=10) == 42
        assert sleep_mock.call_count == 1
        assert 8.8 < sleep_mock.call_args[0][0] < 9.1

        sleep_mock.reset_mock()
        # This moves the clock by 5 second, so we only throttle by 5s
        assert await worker._throttle(throttled_func, throttle_secs=10, x=5) == 42
        assert sleep_mock.call_count == 1
        assert 4.8 < sleep_mock.call_args[0][0] < 5.1

        t.move_to("2022-09-01 05:01:00 +00:00")
        sleep_mock.reset_mock()
        # Throttle for more than 5m (1 timeframe)
        assert await worker._throttle(throttled_func, throttle_secs=400, x=5) == 42
        assert sleep_mock.call_count == 1
        assert 394.8 < sleep_mock.call_args[0][0] < 395.1

        t.move_to("2022-09-01 05:01:00 +00:00")

        sleep_mock.reset_mock()
        # Throttle for more than 5m (1 timeframe)
        assert (
            await worker._throttle(
                throttled_func, throttle_secs=400, timeframe="5m", timeframe_offset=0.4, x=5
            )
            == 42
        )
        assert sleep_mock.call_count == 1
        # 300 (5m) - 60 (1m - see set time above) - 5 (duration of throttled_func) = 235
        assert 235.2 < sleep_mock.call_args[0][0] < 235.6

        t.move_to("2022-09-01 05:04:51 +00:00")
        sleep_mock.reset_mock()
        # Offset of 5s, so we hit the sweet-spot between "candle" and "candle offset"
        # Which should not get a throttle iteration to avoid late candle fetching
        assert (
            await worker._throttle(
                throttled_func, throttle_secs=10, timeframe="5m", timeframe_offset=5, x=1.2
            )
            == 42
        )
        assert sleep_mock.call_count == 1
        # Time is slightly bigger than throttle secs due to the high timeframe offset.
        assert 11.1 < sleep_mock.call_args[0][0] < 13.2


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
    mocker.patch("freqtrade.worker.Worker._throttle", mock_throttle)
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
    mocker.patch("freqtrade.worker.Worker._throttle", mock_throttle)
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


async def test_worker_reload_config(mocker, default_conf) -> None:
    worker = await get_patched_worker(mocker, default_conf)

    # # Simulate Running, reload, running workflow
    worker_mock = get_mock_coro(
        side_effect=[
            State.RUNNING,
            State.RELOAD_CONFIG,
            State.RUNNING,
            OperationalException("Oh snap!"),
        ]
    )
    mocker.patch("freqtrade.worker.Worker._worker", worker_mock)
    reconfigure_mock = mocker.patch("freqtrade.worker.Worker._reconfigure", get_mock_coro())

    with pytest.raises(OperationalException, match="Oh snap!"):
        await worker.run()

    assert worker_mock.call_count == 4
    assert reconfigure_mock.call_count == 1


async def test_worker_reconfigure(mocker, default_conf) -> None:
    worker = await get_patched_worker(mocker, default_conf)
    mocker.patch("freqtrade.freqtradebot.FreqtradeBot.cleanup", get_mock_coro())
    mocker.patch("freqtrade.worker.Worker.init_worker", get_mock_coro())
    notify_mock = mocker.patch("freqtrade.worker.Worker._notify")
    mocker.patch("freqtrade.freqtradebot.RPCManager", MagicMock())

    await worker._reconfigure()
    assert notify_mock.call_count == 2
