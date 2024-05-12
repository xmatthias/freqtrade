import logging
import signal
from typing import Any, Dict


logger = logging.getLogger(__name__)


async def start_trading(args: Dict[str, Any]) -> int:
    """
    Main entry point for trading mode
    """
    # Import here to avoid loading worker module when it's not used
    from freqtrade.worker import Worker

    def term_handler(signum, frame):
        # Raise KeyboardInterrupt - so we can handle it in the same way as Ctrl-C
        raise KeyboardInterrupt()

    # Create and run worker
    worker = None
    try:
        signal.signal(signal.SIGTERM, term_handler)
        worker = Worker(args)
        await worker.init_worker()
        await worker.run()
    finally:
        if worker:
            logger.info("worker found ... calling exit")
            await worker.exit()
    return 0
