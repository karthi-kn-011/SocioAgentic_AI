import time
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from . import models

# --- Posts ---

def create_post(
    db: Session,
    topic: str,
    tone: str = "Professional & Engaging",
    target_platforms: Optional[List[str]] = None,
    platform_contents: Optional[Dict[str, str]] = None,
    raw_content: Optional[str] = None,
    status: models.PostStatus = models.PostStatus.DRAFT,
    thread_id: Optional[str] = None
) -> models.Post:
    post = models.Post(
        topic=topic,
        tone=tone,
        target_platforms=target_platforms or [],
        platform_contents=platform_contents or {},
        raw_content=raw_content,
        status=status,
        thread_id=thread_id
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post

def get_post_by_id(db: Session, post_id: int) -> Optional[models.Post]:
    return db.query(models.Post).filter(models.Post.id == post_id).first()

def get_posts(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    status: Optional[models.PostStatus] = None
) -> List[models.Post]:
    query = db.query(models.Post)
    if status:
        query = query.filter(models.Post.status == status)
    return query.order_by(models.Post.created_at.desc()).offset(skip).limit(limit).all()

def update_post(db: Session, post_id: int, **kwargs) -> Optional[models.Post]:
    post = get_post_by_id(db, post_id)
    if not post:
        return None
    for key, value in kwargs.items():
        if hasattr(post, key) and value is not None:
            setattr(post, key, value)
    db.commit()
    db.refresh(post)
    return post

def delete_post(db: Session, post_id: int) -> bool:
    post = get_post_by_id(db, post_id)
    if not post:
        return False
    db.delete(post)
    db.commit()
    return True

# --- Approval Requests ---

def create_approval_request(
    db: Session,
    post_id: int,
    channel: str = "web",
    message_ts: Optional[str] = None,
    status: str = "PENDING"
) -> models.ApprovalRequest:
    approval = models.ApprovalRequest(
        post_id=post_id,
        channel=channel,
        message_ts=message_ts,
        status=status
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval

# --- Social Accounts ---

def upsert_social_account(
    db: Session,
    platform: models.PlatformType,
    account_name: str,
    account_id: Optional[str] = None,
    encrypted_access_token: Optional[str] = None,
    encrypted_refresh_token: Optional[str] = None,
    is_active: bool = True
) -> models.SocialAccount:
    account = db.query(models.SocialAccount).filter(models.SocialAccount.platform == platform).first()
    if account:
        account.account_name = account_name
        if account_id:
            account.account_id = account_id
        if encrypted_access_token:
            account.encrypted_access_token = encrypted_access_token
        if encrypted_refresh_token:
            account.encrypted_refresh_token = encrypted_refresh_token
        account.is_active = is_active
    else:
        account = models.SocialAccount(
            platform=platform,
            account_name=account_name,
            account_id=account_id,
            encrypted_access_token=encrypted_access_token,
            encrypted_refresh_token=encrypted_refresh_token,
            is_active=is_active
        )
        db.add(account)
    db.commit()
    db.refresh(account)
    return account

def get_social_accounts(db: Session) -> List[models.SocialAccount]:
    return db.query(models.SocialAccount).all()

def get_social_account_by_platform(db: Session, platform: models.PlatformType) -> Optional[models.SocialAccount]:
    return db.query(models.SocialAccount).filter(models.SocialAccount.platform == platform).first()

# --- Publish Logs ---

def create_publish_log(
    db: Session,
    post_id: int,
    platform: models.PlatformType,
    status: str,
    external_post_id: Optional[str] = None,
    response_payload: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None
) -> models.PublishLog:
    log = models.PublishLog(
        post_id=post_id,
        platform=platform,
        status=status,
        external_post_id=external_post_id,
        response_payload=response_payload,
        error_message=error_message
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

# --- Activity Log ---

def log_activity(
    db: Session,
    action: str,
    details: Optional[str] = None,
    post_id: Optional[int] = None,
    actor: str = "System"
) -> models.ActivityLog:
    log = models.ActivityLog(
        action=action,
        details=details,
        post_id=post_id,
        actor=actor
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

# --- OAuth State & PKCE Persistence (Database-backed, TTL Expiration) ---

def store_oauth_state(
    db: Session,
    state: str,
    platform: str,
    code_verifier: Optional[str] = None,
    redirect_uri: Optional[str] = None,
    ttl_seconds: int = 600
) -> models.OAuthState:
    clean_expired_oauth_states(db)
    oauth_state = models.OAuthState(
        state=state,
        platform=platform.upper(),
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
        expires_at=time.time() + ttl_seconds
    )
    db.merge(oauth_state)
    db.commit()
    return oauth_state

def get_and_consume_oauth_state(db: Session, state: str) -> Optional[models.OAuthState]:
    clean_expired_oauth_states(db)
    record = db.query(models.OAuthState).filter(models.OAuthState.state == state).first()
    if not record:
        return None
    # Check if expired
    if record.expires_at < time.time():
        db.delete(record)
        db.commit()
        return None
    # Consume (one-time use)
    state_copy = models.OAuthState(
        state=record.state,
        platform=record.platform,
        code_verifier=record.code_verifier,
        redirect_uri=record.redirect_uri,
        expires_at=record.expires_at
    )
    db.delete(record)
    db.commit()
    return state_copy

def clean_expired_oauth_states(db: Session):
    now = time.time()
    db.query(models.OAuthState).filter(models.OAuthState.expires_at < now).delete(synchronize_session=False)
    db.commit()
