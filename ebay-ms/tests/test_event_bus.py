"""tests/test_event_bus.py — EventBus + AuditLog 单元测试"""


from core.database.connection import get_session
from core.events.bus import EventBus, get_event_bus
from core.events.models import EventLog, EventStatus
from core.security.audit import AuditLog, audit_log

# ── 辅助 ────────────────────────────────────────────────────


def _event_count(status: EventStatus | None = None) -> int:
    with get_session() as s:
        q = s.query(EventLog)
        if status:
            q = q.filter(EventLog.status == status)
        return q.count()


def _clear_events() -> None:
    with get_session() as s:
        s.query(EventLog).delete()
        s.commit()


# ── EventBus 测试 ────────────────────────────────────────────


class TestEventBusBasics:
    """发布/订阅基础测试"""

    def setup_method(self):
        _clear_events()
        # 强制重建单例（避免跨测试状态）
        EventBus._instance = None

    def test_publish_creates_pending_record(self):
        # Publishing creates a record in DB with id assigned.
        # Status is PENDING at moment of insert, then immediately updated to DONE (no handler).
        # We verify record exists with a valid id and correct metadata.
        bus = get_event_bus()
        ev = bus.publish("TEST_EVENT", {"key": "value"})
        assert ev.id is not None
        assert ev.event_type == "TEST_EVENT"
        assert ev.payload == {"key": "value"}
        # No handler registered → auto DONE
        assert ev.status == EventStatus.DONE

    def test_publish_no_handler_marks_done(self):
        bus = get_event_bus()
        ev = bus.publish("NO_HANDLER_EVENT", {})
        assert ev.status == EventStatus.DONE

    def test_subscribe_and_dispatch(self):
        bus = get_event_bus()
        received = []

        def handler(event_type, payload):
            received.append((event_type, payload))

        bus.subscribe("MY_EVENT", handler)
        ev = bus.publish("MY_EVENT", {"data": 42})

        assert len(received) == 1
        assert received[0] == ("MY_EVENT", {"data": 42})
        assert ev.status == EventStatus.DONE

    def test_multiple_handlers(self):
        bus = get_event_bus()
        results = []

        bus.subscribe("MULTI", lambda et, pl: results.append(1))
        bus.subscribe("MULTI", lambda et, pl: results.append(2))
        bus.publish("MULTI", {})

        assert len(results) == 2
        # status 取决于最后一个 handler，这里两个都成功则 done
        assert results == [1, 2]


class TestEventBusPersistence:
    """事件持久化 + 状态迁移"""

    def setup_method(self):
        _clear_events()
        EventBus._instance = None

    def test_published_event_logged_in_db(self):
        bus = get_event_bus()
        ev = bus.publish("PERSISTENCE_TEST", {"x": 1})
        with get_session() as s:
            db_ev = s.get(EventLog, ev.id)
        assert db_ev is not None
        assert db_ev.event_type == "PERSISTENCE_TEST"

    def test_handler_failure_sets_failed(self):
        bus = get_event_bus()

        def bad_handler(et, pl):
            raise RuntimeError("intentional")

        bus.subscribe("FAIL_EVENT", bad_handler)
        ev = bus.publish("FAIL_EVENT", {})

        assert ev.status == EventStatus.FAILED
        assert ev.error_message is not None
        assert "intentional" in ev.error_message

    def test_handler_failure_increments_retry_count(self):
        bus = get_event_bus()

        def bad_handler(et, pl):
            raise RuntimeError("fail")

        bus.subscribe("RETRY_TEST", bad_handler)
        ev = bus.publish("RETRY_TEST", {})

        assert ev.retry_count == 1
        assert ev.status == EventStatus.FAILED

    def test_handler_success_marks_done(self):
        bus = get_event_bus()
        bus.subscribe("SUCCESS_EVENT", lambda et, pl: None)
        ev = bus.publish("SUCCESS_EVENT", {})
        assert ev.status == EventStatus.DONE

    def test_dead_letter_after_max_retries(self):
        with get_session() as s:
            ev = EventLog(
                event_type="DEAD_LETTER_TEST",
                payload={},
                status=EventStatus.FAILED,
                retry_count=3,
                max_retries=3,
            )
            s.add(ev)
            s.commit()
            ev_id = ev.id

        bus = get_event_bus()
        bus.mark_dead_letter(ev_id, "max retries exhausted")

        with get_session() as s:
            db_ev = s.get(EventLog, ev_id)
        assert db_ev.status == EventStatus.DEAD_LETTER


class TestEventBusRetry:
    """自动重试逻辑"""

    def setup_method(self):
        _clear_events()
        EventBus._instance = None

    def test_retry_pending_on_startup(self):
        """启动时 pending 事件应该被重新分发"""
        with get_session() as s:
            ev = EventLog(event_type="STARTUP_RETRY", payload={}, status=EventStatus.PENDING)
            s.add(ev)
            s.commit()
            ev_id = ev.id

        bus = get_event_bus()
        received = []

        def handler(et, pl):
            received.append(et)

        bus.subscribe("STARTUP_RETRY", handler)
        bus.retry_pending()

        assert len(received) == 1
        with get_session() as s:
            db_ev = s.get(EventLog, ev_id)
        assert db_ev.status == EventStatus.DONE


# ── AuditLog 测试 ────────────────────────────────────────────


class TestAuditLog:
    """审计日志测试"""

    def setup_method(self):
        with get_session() as s:
            s.query(AuditLog).delete()
            s.commit()

    def test_audit_log_creates_record(self):
        record = audit_log(
            action="test_action",
            operator="test_user",
            detail={"key": "value"},
        )
        assert record.id is not None
        assert record.action == "test_action"
        assert record.operator == "test_user"
        assert record.detail == {"key": "value"}

    def test_audit_log_minimal(self):
        record = audit_log(action="minimal", operator="user")
        assert record.action == "minimal"
        assert record.detail == {}

    def test_audit_log_queryable(self):
        audit_log(action="query_test", operator="admin", detail={"x": 1})
        with get_session() as s:
            records = s.query(AuditLog).filter(AuditLog.action == "query_test").all()
        assert len(records) == 1
        assert records[0].operator == "admin"
