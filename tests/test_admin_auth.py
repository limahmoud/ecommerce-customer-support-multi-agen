from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.api import app
from database.db import SessionLocal
from database.models import User, AuditLog
from security.dependencies import get_db, get_current_user


@pytest.fixture
def admin_context():
    db = SessionLocal()

    suffix = uuid4().hex

    admin = User(
        email=f"admin-test-{suffix}@example.com",
        hashed_password="not-used",
        role="admin",
        customer_id=None,
        is_active=True,
    )

    db.add(admin)
    db.commit()
    db.refresh(admin)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin

    try:
        with TestClient(app) as client:
            yield client, db, admin

    finally:
        app.dependency_overrides.clear()

        db.query(AuditLog).filter(
            AuditLog.actor_user_id == admin.id
        ).delete(synchronize_session=False)

        db.query(User).filter(
            User.email.like("admin-test-%")
        ).delete(synchronize_session=False)

        db.commit()
        db.close()


def test_admin_can_list_users(admin_context):
    client, db, admin = admin_context

    response = client.get("/auth/users")

    assert response.status_code == 200

    users = response.json()

    assert any(user["id"] == admin.id for user in users)


def test_admin_can_create_staff_user(admin_context):
    client, db, admin = admin_context

    email = f"admin-test-staff-{uuid4().hex}@example.com"

    response = client.post(
        "/auth/users",
        json={
            "email": email,
            "password": "TestPassword123",
            "role": "support_agent",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == email
    assert response.json()["role"] == "support_agent"

    user = db.query(User).filter(
        User.email == email
    ).first()

    assert user is not None

    audit = db.query(AuditLog).filter(
        AuditLog.actor_user_id == admin.id,
        AuditLog.action == "create_user",
        AuditLog.entity_id == str(user.id),
    ).first()

    assert audit is not None
    assert audit.new_value["role"] == "support_agent"


def test_admin_can_update_user_role(admin_context):
    client, db, admin = admin_context

    email = f"admin-test-update-{uuid4().hex}@example.com"

    user = User(
        email=email,
        hashed_password="not-used",
        role="support_agent",
        customer_id=None,
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    response = client.patch(
        f"/auth/users/{user.id}",
        json={"role": "returns_agent"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "returns_agent"

    audit = db.query(AuditLog).filter(
        AuditLog.actor_user_id == admin.id,
        AuditLog.action == "update_user",
        AuditLog.entity_id == str(user.id),
    ).first()

    assert audit is not None
    assert audit.old_value["role"] == "support_agent"
    assert audit.new_value["role"] == "returns_agent"


@pytest.mark.parametrize(
    "role",
    [
        "customer",
        "support_agent",
        "returns_agent",
        "shipping_agent",
    ],
)
def test_non_admin_cannot_manage_users(admin_context, role):
    from types import SimpleNamespace

    client, db, admin = admin_context

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=9999,
        email="staff@example.com",
        role=role,
        is_active=True,
    )

    response = client.get("/auth/users")

    assert response.status_code == 403


def test_admin_cannot_change_own_role(admin_context):
    client, db, admin = admin_context

    response = client.patch(
        f"/auth/users/{admin.id}",
        json={"role": "support_agent"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "You cannot change your own role."
    )


def test_admin_cannot_deactivate_own_account(admin_context):
    client, db, admin = admin_context

    response = client.patch(
        f"/auth/users/{admin.id}",
        json={"is_active": False},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "You cannot deactivate your own account."
    )


def test_admin_cannot_assign_invalid_role(admin_context):
    client, db, admin = admin_context

    email = f"invalid-role-{uuid4().hex}@example.com"

    response = client.post(
        "/auth/users",
        json={
            "email": email,
            "password": "TestPassword123",
            "role": "supervisor",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid staff role."

    assert db.query(User).filter(
        User.email == email
    ).first() is None


def test_admin_cannot_update_user_with_invalid_role(admin_context):
    client, db, admin = admin_context

    email = f"invalid-update-{uuid4().hex}@example.com"

    user = User(
        email=email,
        hashed_password="not-used",
        role="support_agent",
        customer_id=None,
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    response = client.patch(
        f"/auth/users/{user.id}",
        json={"role": "customer"},
    )

    assert response.status_code == 400

    db.refresh(user)
    assert user.role == "support_agent"


def test_admin_cannot_update_without_changes(admin_context):
    client, db, admin = admin_context

    response = client.patch(
        f"/auth/users/{admin.id}",
        json={},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "No changes were provided."
    )


def test_admin_cannot_update_nonexistent_user(admin_context):
    client, db, admin = admin_context

    response = client.patch(
        "/auth/users/999999999",
        json={"is_active": False},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


def test_admin_cannot_demote_last_active_admin(admin_context):
    from types import SimpleNamespace

    client, db, admin = admin_context
    admin.is_active = False
    db.commit()

    last_admin = User(
        email=f"admin-test-last-{uuid4().hex}@example.com",
        hashed_password="not-used",
        role="admin",
        customer_id=None,
        is_active=True,
    )

    db.add(last_admin)
    db.commit()
    db.refresh(last_admin)

    # Simulate an authenticated admin not stored in this test DB.
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=999999,
        email="external-admin@example.com",
        role="admin",
        is_active=True,
    )

    response = client.patch(
        f"/auth/users/{last_admin.id}",
        json={"role": "support_agent"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Cannot modify the last active admin."
    )

    db.refresh(last_admin)
    assert last_admin.role == "admin"


def test_admin_cannot_deactivate_last_active_admin(admin_context):
    from types import SimpleNamespace

    client, db, admin = admin_context
    admin.is_active = False
    db.commit()

    last_admin = User(
        email=f"admin-test-last-{uuid4().hex}@example.com",
        hashed_password="not-used",
        role="admin",
        customer_id=None,
        is_active=True,
    )

    db.add(last_admin)
    db.commit()
    db.refresh(last_admin)

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=999999,
        email="external-admin@example.com",
        role="admin",
        is_active=True,
    )

    response = client.patch(
        f"/auth/users/{last_admin.id}",
        json={"is_active": False},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Cannot modify the last active admin."
    )

    db.refresh(last_admin)
    assert last_admin.is_active is True



def test_admin_can_list_audit_logs(admin_context):
    client, db, admin = admin_context

    email = f"admin-test-audit-{uuid4().hex}@example.com"

    client.post(
        "/auth/users",
        json={
            "email": email,
            "password": "TestPassword123",
            "role": "support_agent",
        },
    )

    response = client.get("/auth/audit-logs")

    assert response.status_code == 200

    logs = response.json()

    assert len(logs) >= 1
    assert any(log["action"] == "create_user" for log in logs)


def test_audit_logs_are_ordered_newest_first(admin_context):
    from datetime import datetime, timedelta, timezone

    client, db, admin = admin_context

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    older_log = AuditLog(
        actor_user_id=admin.id,
        actor_email=admin.email,
        actor_role="admin",
        action="older_action",
        entity_type="user",
        created_at=now - timedelta(minutes=10),
    )

    newer_log = AuditLog(
        actor_user_id=admin.id,
        actor_email=admin.email,
        actor_role="admin",
        action="newer_action",
        entity_type="user",
        created_at=now,
    )

    db.add_all([older_log, newer_log])
    db.commit()

    response = client.get("/auth/audit-logs")

    assert response.status_code == 200

    actions = [log["action"] for log in response.json()]

    assert actions.index("newer_action") < actions.index("older_action")


def test_non_admin_cannot_view_audit_logs(admin_context):
    from types import SimpleNamespace

    client, db, admin = admin_context

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=9999,
        email="staff@example.com",
        role="support_agent",
        is_active=True,
    )

    response = client.get("/auth/audit-logs")

    assert response.status_code == 403


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
    ],
)
def test_audit_logs_reject_invalid_pagination(admin_context, params):
    client, db, admin = admin_context

    response = client.get("/auth/audit-logs", params=params)

    assert response.status_code == 400