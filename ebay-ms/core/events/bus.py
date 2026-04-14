"""EventBus — 事件总线单例，发布/订阅 + 持久化 + 重试 + dead_letter"""
import threading
import time
from datetime import datetime, timezone
from typing import Callable

from core.database.connection import get_session
from core.events.models import EventLog, EventStatus
from core.utils.logger import get_logger

log = get_logger("event_bus")


class EventBus:
    """事件总线 — 发布/订阅 + 事件持久化 + 自动重试"""

    _instance: "EventBus | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._handlers: dict[str, list[Callable]] = {}  # event_type -> [handlers]
        self._handler_lock = threading.RLock()
        self._retry_thread: threading.Thread | None = None
        self._stop_retry = threading.Event()
        self._initialized = True
        log.info("EventBus initialized")

    # ── 订阅 ──────────────────────────────────────────────

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """注册事件处理器"""
        with self._handler_lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)
        log.debug(f"Subscribed handler to {event_type}")

    # ── 发布 ──────────────────────────────────────────────

    def publish(self, event_type: str, payload: dict | None = None) -> EventLog:
        """
        发布事件：先写入 event_log(status=PENDING)，再分发给 handler。
        即使 handler 失败，事件也不会丢失。
        """
        payload = payload or {}

        # 在 session 中创建记录
        with get_session() as s:
            record = EventLog(
                event_type=event_type,
                payload=payload,
                status=EventStatus.PENDING,
                retry_count=0,
            )
            s.add(record)
            s.commit()
            record_id = record.id

        log.debug(f"Published event {event_type} (id={record_id})")

        # 同步分发 handler（捕获异常，不向上扩散）
        self._dispatch(record_id, event_type, payload)

        # 重新获取以返回最新状态
        with get_session() as s:
            record = s.get(EventLog, record_id)

        return record

    # ── 分发 ──────────────────────────────────────────────

    def _dispatch(self, event_id: int, event_type: str, payload: dict) -> None:
        """将事件分发给所有已注册的 handler"""
        with self._handler_lock:
            handlers = list(self._handlers.get(event_type, []))

        if not handlers:
            # 无 handler，记录但标记为 done
            with get_session() as s:
                ev = s.get(EventLog, event_id)
                if ev and ev.status == EventStatus.PENDING:
                    ev.status = EventStatus.DONE
                    ev.processed_at = datetime.now(timezone.utc)
                    s.commit()
            log.debug(f"No handler for {event_type}, marked done")
            return

        errors = []
        for handler in handlers:
            try:
                handler(event_type, payload)
            except Exception as exc:
                errors.append(str(exc))
                log.error(f"Handler {handler.__name__} failed for {event_type}: {exc}")

        with get_session() as s:
            ev = s.get(EventLog, event_id)
            if not ev or ev.status != EventStatus.PENDING:
                return

            if errors:
                ev.status = EventStatus.FAILED
                ev.error_message = "; ".join(errors)
                ev.retry_count += 1
                log.warning(f"Event {event_type} failed (retry={ev.retry_count})")
            else:
                ev.status = EventStatus.DONE
                ev.processed_at = datetime.now(timezone.utc)
                log.debug(f"Event {event_type} processed successfully")

            s.commit()

    # ── 启动时重试 ──────────────────────────────────────────

    def retry_pending(self) -> None:
        """重启时自动重试 PENDING 和 FAILED 事件（最多 max_retries）"""
        with get_session() as s:
            events = (
                s.query(EventLog)
                .filter(
                    EventLog.status.in_([EventStatus.PENDING, EventStatus.FAILED]),
                    EventLog.retry_count < EventLog.max_retries,
                )
                .order_by(EventLog.created_at)
                .all()
            )

        log.info(f"Retrying {len(events)} pending/failed events on startup")
        for ev in events:
            # 短暂延迟避免同时大量重试
            time.sleep(0.1)
            self._dispatch(ev.id, ev.event_type, ev.payload)

    def mark_dead_letter(self, event_id: int, error: str) -> None:
        """标记为 dead_letter（重试次数耗尽）"""
        with get_session() as s:
            ev = s.get(EventLog, event_id)
            if ev:
                ev.status = EventStatus.DEAD_LETTER
                ev.error_message = error
                s.commit()
        log.warning(f"Event id={event_id} moved to dead_letter: {error}")

    # ── 后台重试线程 ──────────────────────────────────────────

    def start_retry_worker(self, interval: float = 30.0) -> None:
        """启动后台线程，定期扫描 failed 事件并重试"""
        if self._retry_thread and self._retry_thread.is_alive():
            return

        self._stop_retry.clear()
        self._retry_thread = threading.Thread(
            target=self._retry_loop, args=(interval,), daemon=True, name="event-retry"
        )
        self._retry_thread.start()
        log.info("Retry worker started")

    def stop_retry_worker(self) -> None:
        self._stop_retry.set()
        if self._retry_thread:
            self._retry_thread.join(timeout=5)
        log.info("Retry worker stopped")

    def _retry_loop(self, interval: float) -> None:
        while not self._stop_retry.wait(interval):
            with get_session() as s:
                failed = (
                    s.query(EventLog)
                    .filter(
                        EventLog.status == EventStatus.FAILED,
                        EventLog.retry_count < EventLog.max_retries,
                    )
                    .all()
                )

            for ev in failed:
                with get_session() as s:
                    # re-fetch with session lock
                    event = s.get(EventLog, ev.id)
                    if not event or event.status != EventStatus.FAILED:
                        continue
                    if event.retry_count >= event.max_retries:
                        event.status = EventStatus.DEAD_LETTER
                        s.commit()
                        log.warning(f"Event {event.event_type} exhausted retries → dead_letter")
                        continue

                time.sleep(1.0)
                self._dispatch(ev.id, ev.event_type, ev.payload)


# ── 全局单例访问点 ──────────────────────────────────────────

_event_bus_instance: EventBus | None = None
_instance_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """返回全局 EventBus 单例"""
    global _event_bus_instance
    if _event_bus_instance is None:
        with _instance_lock:
            if _event_bus_instance is None:
                _event_bus_instance = EventBus()
    return _event_bus_instance
