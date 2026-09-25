# -*- coding: utf-8 -*-
"""
服务检测 / 测速双线调度 (参考 subs-check 的分段流水线: 节点测活通过即进入后续阶段，各阶段独立并发)。

- 两条线各有独立的工作线程与任务队列，节点判活后立即分别入队，不等整批；
- 资源互斥: 任务声明占用的节点 (及其前置)。测速任务不与任何正在进行的任务共用节点，
  服务任务不与正在测速的节点共用 (同一节点可同时跑多个服务任务)，避免同一节点既被测速又被检测而互相拖慢;
- 静默任务 (quiet): 仅在服务线全部结束后才执行，用于受并行流量干扰的测速在链路空闲时重测;
- 生产者计数: 仍可能有新任务加入某条线时 (测活未完、落地测速待定)，该线工作线程等待而不退出。
"""
import threading
import time

SERVICE, SPEED = "service", "speed"


class Job:
    def __init__(self, run, resources=(), quiet=False, tag=None, name=None):
        self.run = run
        self.resources = frozenset(resources)
        self.quiet = quiet
        self.tag = tag
        self.name = name
        self.error = None


class DualLineScheduler:
    def __init__(self, service_workers, speed_workers, on_error=None):
        self._workers = {SERVICE: max(0, service_workers), SPEED: max(0, speed_workers)}
        self._cond = threading.Condition()
        self._queues = {SERVICE: [], SPEED: []}
        self._active = {SERVICE: [], SPEED: []}
        self._producers = {SERVICE: 0, SPEED: 0}
        self._service_spans = []   # (开始, 结束) monotonic，结束为 None 表示仍在进行
        self._threads = []
        self._on_error = on_error

    # ---- 生产者与任务 ----
    def open_producer(self, *lines):
        with self._cond:
            for line in lines:
                self._producers[line] += 1

    def close_producer(self, *lines):
        with self._cond:
            for line in lines:
                self._producers[line] -= 1
            self._cond.notify_all()

    def add(self, line, job):
        with self._cond:
            self._queues[line].append(job)
            self._cond.notify_all()

    # ---- 状态查询 ----
    def service_finished(self):
        with self._cond:
            return self._service_finished()

    def _service_finished(self):
        return not self._queues[SERVICE] and not self._active[SERVICE] and self._producers[SERVICE] <= 0

    def pending(self, line, predicate=lambda job: True):
        """line 上排队或进行中且满足 predicate 的任务数。"""
        with self._cond:
            return sum(1 for job in self._queues[line] + self._active[line] if predicate(job))

    def wait_until(self, predicate, poll=1.0):
        """阻塞直到 predicate(scheduler) 为真 (状态变化或每 poll 秒复查一次)。"""
        with self._cond:
            while not predicate(self):
                self._cond.wait(poll)

    def service_busy(self, start, end):
        """[start, end] 内是否有服务任务在进行 (流量统计缺失时的保守判据)。"""
        with self._cond:
            now = time.monotonic()
            return any(s <= end and (e if e is not None else now) >= start for s, e in self._service_spans)

    # ---- 调度 ----
    def _busy_resources(self, line):
        busy = set()
        lines = (SERVICE, SPEED) if line == SPEED else (SPEED,)
        for other in lines:
            for job in self._active[other]:
                busy |= job.resources
        return busy

    def _pick(self, line):
        busy = self._busy_resources(line)
        if line == SPEED:
            quiet_ok = self._service_finished()
            for job in self._queues[SPEED]:
                if (job.quiet and not quiet_ok) or job.resources & busy:
                    continue
                return job
            return None
        # 服务线: 不占用测速线接下来要测的节点 (测速线串行、是整体瓶颈，不能让它空等)，
        # 并优先检测已无待测速任务的节点，把尚未测速的节点留给测速线
        reserved = self._speed_reservations()
        pending_speed = set()
        for job in self._queues[SPEED]:
            pending_speed |= job.resources
        fallback = None
        for job in self._queues[SERVICE]:
            if job.resources & (busy | reserved):
                continue
            if not job.resources & pending_speed:
                return job
            if fallback is None:
                fallback = job
        return fallback

    def _speed_reservations(self):
        """测速线下一批可立即开测的任务 (数量 = 测速并发) 所占节点。"""
        busy = self._busy_resources(SPEED)
        reserved, count = set(), 0
        for job in self._queues[SPEED]:
            if count >= self._workers[SPEED]:
                break
            if job.quiet or job.resources & busy:
                continue
            reserved |= job.resources
            count += 1
        return reserved

    def _line_done(self, line):
        return not self._queues[line] and self._producers[line] <= 0

    def _worker(self, line):
        while True:
            with self._cond:
                while True:
                    job = self._pick(line)
                    if job is not None:
                        break
                    if self._line_done(line):
                        self._cond.notify_all()
                        return
                    self._cond.wait(1.0)
                self._queues[line].remove(job)
                self._active[line].append(job)
                span = None
                if line == SERVICE:
                    span = [time.monotonic(), None]
                    self._service_spans.append(span)
            try:
                job.run()
            except Exception as error:  # 任务自身应处理异常；兜底记录，不让一个节点拖垮整条线
                job.error = f"{type(error).__name__}: {error}"
                if self._on_error:
                    self._on_error(line, job)
            finally:
                with self._cond:
                    self._active[line].remove(job)
                    if span is not None:
                        span[1] = time.monotonic()
                    self._cond.notify_all()

    def start(self):
        for line, count in self._workers.items():
            for index in range(count):
                thread = threading.Thread(target=self._worker, args=(line,), daemon=True,
                                          name=f"{line}-{index}")
                thread.start()
                self._threads.append(thread)

    def join(self):
        for thread in self._threads:
            thread.join()
