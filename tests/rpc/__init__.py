from freqtrade.rpc.rpc import RPC


def patch_run_async(rpc: RPC):
    """
    Patch run async to not require lock.
    """
    orig = rpc._run_async

    def _run_async_mock(coro, require_lock=False):
        return orig(coro, require_lock=False)

    rpc._run_async = _run_async_mock
