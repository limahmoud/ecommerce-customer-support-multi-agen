from sqlalchemy.orm import Session

from database.models import AuditLog


def log_admin_action(
    db: Session,
    actor,
    action: str,
    entity_type: str,
    entity_id: int | str | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
):
    log = AuditLog(
        actor_user_id=actor.id,
        actor_email=actor.email,
        actor_role=actor.role,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        old_value=old_value,
        new_value=new_value,
    )

    db.add(log)
    db.flush()

    return log
