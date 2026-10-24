from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.command_parser import CommandParser, ParsedCommand
from app.core.queue_manager import QueueManager
from app.models import Base, Task
from app.models.task import TaskPriority, TaskStatus, TaskType
from app.services.llm_service import LLMService


@pytest.fixture
def db_session():
    """Use an isolated in-memory database for each test."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def parsed_command(**overrides) -> ParsedCommand:
    values = {
        "task_type": TaskType.GENERAL,
        "title": "Summarize a report",
        "description": "Summarize the supplied report.",
        "priority": TaskPriority.MEDIUM,
        "target_service": "general_service",
        "service_endpoint": "",
        "parameters": {},
        "confidence": 0.9,
    }
    values.update(overrides)
    return ParsedCommand(**values)


def make_task(title: str, priority: TaskPriority = TaskPriority.MEDIUM) -> Task:
    return Task(
        title=title,
        description=f"Test task: {title}",
        command=f"Run {title}",
        task_type=TaskType.GENERAL,
        priority=priority,
        target_service="general_service",
        parameters={},
    )


def test_command_parser_accepts_a_complete_general_command():
    parser = CommandParser()

    assert parser.validate_parsed_command(parsed_command()) is True


def test_command_parser_rejects_an_empty_title():
    parser = CommandParser()

    assert parser.validate_parsed_command(parsed_command(title="")) is False


def test_command_parser_rejects_low_confidence():
    parser = CommandParser()

    assert parser.validate_parsed_command(parsed_command(confidence=0.49)) is False


def test_command_parser_rejects_browser_task_routed_to_wrong_service():
    parser = CommandParser()
    command = parsed_command(
        task_type=TaskType.BROWSER_AUTOMATION,
        target_service="document_service",
    )

    assert parser.validate_parsed_command(command) is False


@pytest.mark.parametrize(
    ("priority", "expected_score"),
    [
        (TaskPriority.LOW, 1.0),
        (TaskPriority.MEDIUM, 2.0),
        (TaskPriority.HIGH, 3.0),
        (TaskPriority.URGENT, 4.0),
    ],
)
def test_priority_score_matches_priority(priority, expected_score, db_session):
    queue = QueueManager(db_session)

    assert queue._calculate_priority_score(make_task("priority", priority)) == expected_score


@pytest.mark.asyncio
async def test_queue_returns_higher_priority_tasks_first(db_session):
    queue = QueueManager(db_session)
    low = make_task("low", TaskPriority.LOW)
    urgent = make_task("urgent", TaskPriority.URGENT)
    medium = make_task("medium", TaskPriority.MEDIUM)

    assert await queue.add_task(low) is True
    assert await queue.add_task(urgent) is True
    assert await queue.add_task(medium) is True

    assert (await queue.get_next_task()).title == "urgent"
    assert (await queue.get_next_task()).title == "medium"
    assert (await queue.get_next_task()).title == "low"
    assert await queue.get_next_task() is None


@pytest.mark.asyncio
async def test_cancelled_task_is_not_returned_for_processing(db_session):
    queue = QueueManager(db_session)
    task = make_task("cancel me")

    assert await queue.add_task(task) is True
    assert await queue.cancel_task(task.id) is True
    assert task.status == TaskStatus.CANCELLED
    assert await queue.get_next_task() is None


@pytest.mark.asyncio
async def test_queue_status_reports_persisted_task_counts(db_session):
    queue = QueueManager(db_session)
    pending = make_task("pending")
    completed = make_task("completed")
    failed = make_task("failed")

    assert await queue.add_task(pending) is True
    db_session.add_all([completed, failed])
    completed.status = TaskStatus.COMPLETED
    failed.status = TaskStatus.FAILED
    db_session.commit()

    status = queue.get_queue_status()

    assert status["total_pending"] == 1
    assert status["total_processing"] == 0
    assert status["total_completed"] == 1
    assert status["total_failed"] == 1


@pytest.mark.asyncio
async def test_llm_service_fails_clearly_without_an_api_key(monkeypatch):
    service = LLMService()
    monkeypatch.setattr(service, "api_key", None)

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        await service.chat_completion(
            messages=[{"role": "user", "content": "This test must not make a network call."}]
        )



@pytest.mark.asyncio
async def test_processing_executes_configured_service_and_saves_result(db_session):
    queue = QueueManager(db_session)
    task = make_task("route me")
    db_session.add(task)
    db_session.commit()
    queue.active_tasks = 1

    class RouterStub:
        async def route_task(self, routed_task):
            assert routed_task.id == task.id
            routed_task.status = TaskStatus.COMPLETED
            routed_task.result = {"ok": True, "output": "done"}
            return routed_task.result

    queue.task_router = RouterStub()
    await queue._process_task(task)

    saved = db_session.query(Task).filter(Task.id == task.id).one()
    assert saved.status == TaskStatus.COMPLETED
    assert saved.result == {"ok": True, "output": "done"}
    assert saved.started_at is not None
    assert saved.completed_at is not None
    assert queue.active_tasks == 0


@pytest.mark.asyncio
async def test_processing_marks_task_failed_when_service_errors(db_session):
    queue = QueueManager(db_session)
    task = make_task("service unavailable")
    db_session.add(task)
    db_session.commit()
    queue.active_tasks = 1

    class RouterStub:
        async def route_task(self, routed_task):
            raise RuntimeError("service unavailable")

    queue.task_router = RouterStub()
    await queue._process_task(task)

    saved = db_session.query(Task).filter(Task.id == task.id).one()
    assert saved.status == TaskStatus.FAILED
    assert "service unavailable" in saved.error_message
    assert saved.completed_at is not None
    assert queue.active_tasks == 0



@pytest.mark.asyncio
async def test_health_endpoint_works_without_external_services():
    from main import app
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
