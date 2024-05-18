"""
Custom workaround to schedule coroutines with the great schedule package.
"""

from datetime import datetime
from inspect import iscoroutine, iscoroutinefunction

from schedule import CancelJob, Job, Scheduler


class AsyncJob(Job):
    async def run(self):
        self.last_run = datetime.now()
        self._schedule_next_run()
        if self._is_overdue(datetime.now()):
            return CancelJob

        if iscoroutine(self.job_func.func) or iscoroutinefunction(self.job_func.func):
            ret = await self.job_func()
        else:
            ret = self.job_func()
        self.last_run = datetime.now()
        self._schedule_next_run()

        if self._is_overdue(self.next_run):
            return CancelJob
        return ret


class AsyncScheduler(Scheduler):
    async def run_pending(self):
        runnable_jobs = (job for job in self.jobs if job.should_run)

        for job in sorted(runnable_jobs):
            ret = await job.run()

            if isinstance(ret, CancelJob) or ret is CancelJob:
                self.cancel_job(job)

    def every(self, interval=1):
        job = AsyncJob(interval, self)
        return job
