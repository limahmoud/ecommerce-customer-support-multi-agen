from pydantic import BaseModel, ConfigDict, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.models import(
    User,
    Customer,
    AuditLog
) 
from security.dependencies import (
    get_db,
    get_current_user,
    require_roles,
)
from database.audit import log_admin_action
from security.security import (
    hash_password,
    verify_password,
    create_access_token,
)
from datetime import datetime


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# =====================================
# SCHEMAS
# =====================================

class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: str
    customer_id: int | None
    is_active: bool


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None
    actor_email: str
    actor_role: str
    action: str
    entity_type: str
    entity_id: str | None
    old_value: dict | None
    new_value: dict | None
    created_at: datetime

# =====================================
# REGISTER
# =====================================

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    email = str(request.email).strip().lower()

    existing_user = db.query(User).filter(
        User.email == email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        )

    try:
        # Link to an existing customer with the same email,
        # or create a new customer.
        customer = db.query(Customer).filter(
            Customer.email == email
        ).first()

        if customer is None:
            customer = Customer(
                name=request.name.strip(),
                email=email,
            )
            db.add(customer)
            db.flush()

        # A customer can be linked to only one user account.
        linked_user = db.query(User).filter(
            User.customer_id == customer.id
        ).first()

        if linked_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This customer already has a user account.",
            )

        user = User(
            email=email,
            hashed_password=hash_password(request.password),
            role="customer",
            customer_id=customer.id,
            is_active=True,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or customer account already exists.",
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed.",
        )


# =====================================
# LOGIN
# =====================================

@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = form_data.username.strip().lower()

    user = db.query(User).filter(
        User.email == email
    ).first()

    if user is None or not verify_password(
        form_data.password,
        user.hashed_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )

    access_token = create_access_token(
        user_id=user.id,
        role=user.role,
    )

    return TokenResponse(access_token=access_token)


# =====================================
# CURRENT USER
# =====================================

@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


# =====================================
# ADMIN USER MANAGEMENT
# =====================================

ADMIN_MANAGED_ROLES = {
    "admin",
    "support_agent",
    "returns_agent",
    "shipping_agent",
}


class AdminUserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str


class AdminUserUpdateRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None


# =====================================
# LIST USERS
# =====================================

@router.get(
    "/users",
    response_model=list[UserResponse],
)
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    return db.query(User).order_by(User.id).all()


# =====================================
# CREATE STAFF ACCOUNT
# =====================================

@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_staff_user(
    request: AdminUserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    email = str(request.email).strip().lower()
    role = request.role.strip().lower()

    if role not in ADMIN_MANAGED_ROLES:
        raise HTTPException(
            status_code=400,
            detail="Invalid staff role.",
        )

    existing_user = db.query(User).filter(
        User.email == email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already registered.",
        )

    try:
        user = User(
            email=email,
            hashed_password=hash_password(request.password),
            role=role,
            customer_id=None,
            is_active=True,
        )

        db.add(user)
        db.flush()

        log_admin_action(
            db=db,
            actor=current_user,
            action="create_user",
            entity_type="user",
            entity_id=user.id,
            new_value={
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
            },
        )

        db.commit()
        db.refresh(user)

        return user

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email already registered.",
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create user.",
        )


# =====================================
# UPDATE USER ROLE / ACTIVE STATUS
# =====================================

@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
)
def update_user(
    user_id: int,
    request: AdminUserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    if request.role is None and request.is_active is None:
        raise HTTPException(
            status_code=400,
            detail="No changes were provided.",
        )

    user = db.query(User).filter(
        User.id == user_id
    ).with_for_update().first()

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    old_value = {
        "role": user.role,
        "is_active": user.is_active,
    }

    new_role = (
        request.role.strip().lower()
        if request.role is not None
        else user.role
    )

    new_active = (
        request.is_active
        if request.is_active is not None
        else user.is_active
    )

    if new_role not in ADMIN_MANAGED_ROLES:
        raise HTTPException(
            status_code=400,
            detail="Invalid staff role.",
        )

    if new_role != user.role and user.id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot change your own role.",
        )

    if new_active != user.is_active and user.id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot deactivate your own account.",
        )

    if (
        user.role == "admin"
        and user.is_active
        and (new_role != "admin" or not new_active)
    ):
        active_admins = db.query(User).filter(
            User.role == "admin",
            User.is_active.is_(True),
        ).count()

        if active_admins <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot modify the last active admin.",
            )

    try:
        user.role = new_role
        user.is_active = new_active

        new_value = {
            "role": user.role,
            "is_active": user.is_active,
        }

        log_admin_action(
            db=db,
            actor=current_user,
            action="update_user",
            entity_type="user",
            entity_id=user.id,
            old_value=old_value,
            new_value=new_value,
        )

        db.commit()
        db.refresh(user)

        return user

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update user.",
        )


# =====================================
# LIST AUDIT LOGS
# =====================================

@router.get(
    "/audit-logs",
    response_model=list[AuditLogResponse],
)
def list_audit_logs(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 100.",
        )

    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Offset cannot be negative.",
        )

    logs = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return logs        