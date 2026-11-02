import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.database import Base, get_db
from app.db.models import Employee, Engineer, Ticket, TicketUpdate


load_dotenv()

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")

from sqlalchemy.pool import StaticPool

engine = create_engine(
    TEST_DATABASE_URL,
    **({"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
       if TEST_DATABASE_URL == "sqlite://" else {})
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    employee = Employee(
        id=1,
        name="Test Employee",
        email="seed.employee@example.com",
        department="IT"
    )

    engineer = Engineer(
        id=1,
        name="Test Engineer",
        email="seed.engineer@example.com",
        specialization="Network"
    )

    ticket = Ticket(
        id=1,
        employee_id=1,
        engineer_id=1,
        title="Laptop cannot connect to office Wi-Fi",
        description="The laptop detects the Wi-Fi network but fails to connect.",
        category="Network",
        priority="HIGH",
        status="CLOSED"
    )

    update1 = TicketUpdate(
        ticket_id=1,
        engineer_id=1,
        comment="Status changed from OPEN to ASSIGNED",
        old_status="OPEN",
        new_status="ASSIGNED"
    )

    update2 = TicketUpdate(
        ticket_id=1,
        engineer_id=1,
        comment="Status changed from ASSIGNED to IN_PROGRESS",
        old_status="ASSIGNED",
        new_status="IN_PROGRESS"
    )

    update3 = TicketUpdate(
        ticket_id=1,
        engineer_id=1,
        comment="Status changed from IN_PROGRESS to RESOLVED",
        old_status="IN_PROGRESS",
        new_status="RESOLVED"
    )

    update4 = TicketUpdate(
        ticket_id=1,
        engineer_id=1,
        comment="Status changed from RESOLVED to CLOSED",
        old_status="RESOLVED",
        new_status="CLOSED"
    )

    db.add_all([
        employee,
        engineer,
        ticket,
        update1,
        update2,
        update3,
        update4
    ])

    db.commit()

    if engine.dialect.name == "postgresql":
        db.execute(text(
            "SELECT setval(pg_get_serial_sequence('employees', 'id'), "
            "(SELECT MAX(id) FROM employees))"
        ))

        db.execute(text(
            "SELECT setval(pg_get_serial_sequence('engineers', 'id'), "
            "(SELECT MAX(id) FROM engineers))"
        ))

        db.execute(text(
            "SELECT setval(pg_get_serial_sequence('tickets', 'id'), "
            "(SELECT MAX(id) FROM tickets))"
        ))

        db.execute(text(
            "SELECT setval(pg_get_serial_sequence('ticket_updates', 'id'), "
            "(SELECT MAX(id) FROM ticket_updates))"
        ))

    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()