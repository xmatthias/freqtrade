import asyncio
import logging
import time
from threading import Lock


logger = logging.getLogger(__name__)


class FtAsyncLock:
    def __init__(self):
        self.__lock = Lock()

    async def __aenter__(self):
        waited = False
        started = time.time()
        while True:
            if self.__lock.acquire(blocking=False):
                # logger.info("Aquired async compatible Lock")
                break
            await asyncio.sleep(0.001)
            waited = True
            # logger.warning("Couldn't aquire lock, waiting")
        if waited:
            logger.info(f"Waited for async Lock for {time.time() - started:.3f}s")

    async def __aexit__(self, exc_type, exc_value, traceback):
        # logger.info("Releasing async compatible Lock")
        self.__lock.release()
