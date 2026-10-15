import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.database.database import get_db
from backend.app.database.models import PlatformType, SocialAccount, ActivityLog, get_utc_now
from backend.app.auth.oauth_service import OAuthService
from backend.app.auth.twitter_oauth import TwitterOAuthService
from backend.app.auth.linkedin_oauth import LinkedInOAuthService
from backend.app.auth.facebook_oauth import FacebookOAuthService
from backend.app.auth.instagram_oauth import InstagramOAuthService

logger = logging.getLogger("AuthRouter")

router = APIRouter(prefix="/auth", tags=["Authentication & Social Accounts"])


@router.get("/accounts")
def get_connected_accounts(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Returns the connection and credential status for all supported social platforms."""
    settings = get_settings()
    accounts = db.query(SocialAccount).all()
    account_map = {acc.platform.value: acc for acc in accounts}

    result = {}
    for platform in PlatformType:
        acc = account_map.get(platform.value)
        is_connected = bool(acc and acc.is_active and acc.encrypted_access_token)
        result[platform.value] = {
            "platform": platform.value,
            "connected": is_connected,
            "account_name": acc.account_name if acc and is_connected else None,
            "account_id": acc.account_id if acc and is_connected else None,
            "expires_at": acc.token_expires_at.isoformat() if acc and acc.token_expires_at else None,
            "is_mock": settings.MOCK_SOCIAL_PUBLISHING,
        }

    return {
        "success": True,
        "accounts": result,
        "mock_publishing": settings.MOCK_SOCIAL_PUBLISHING,
        "frontend_origin": settings.FRONTEND_ORIGIN,
    }


@router.get("/twitter/authorize")
def twitter_authorize(db: Session = Depends(get_db)) -> Dict[str, str]:
    """Generates PKCE challenge and returns the X (Twitter) OAuth 2.0 authorization URL."""
    settings = get_settings()
    code_verifier, code_challenge = OAuthService.generate_pkce_pair()

    state_rec = OAuthService.create_oauth_state(
        db=db,
        platform="TWITTER",
        code_verifier=code_verifier,
        redirect_uri=settings.X_REDIRECT_URI,
        ttl_seconds=600,
    )

    auth_url = TwitterOAuthService.build_authorization_url(
        state=state_rec.state,
        code_challenge=code_challenge,
        redirect_uri=settings.X_REDIRECT_URI,
    )

    return {
        "authorization_url": auth_url,
        "state": state_rec.state,
    }


def _render_popup_callback_html(status: str, platform: str, account_name: Optional[str] = None, error: Optional[str] = None) -> HTMLResponse:
    """Renders HTML that securely transmits the OAuth result to the parent window using strict origin targeting."""
    settings = get_settings()
    target_origin = settings.FRONTEND_ORIGIN.rstrip("/")

    payload = {
        "type": "SOCIAL_AGENT_OAUTH_CALLBACK",
        "platform": platform,
        "status": status,
        "accountName": account_name or "",
        "error": error or "",
    }
    payload_json = json.dumps(payload)
    target_origin_json = json.dumps(target_origin)

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Authentication Status</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100vh;
      margin: 0;
      background: #09090b;
      color: #fafafa;
      text-align: center;
    }}
    .box {{
      background: #18181b;
      border: 1px solid #27272a;
      border-radius: 12px;
      padding: 32px;
      max-width: 400px;
    }}
    h2 {{ margin-top: 0; font-size: 1.25rem; }}
    p {{ color: #a1a1aa; font-size: 0.875rem; }}
  </style>
</head>
<body>
  <div class="box">
    <h2>{"Authentication Complete" if status == "SUCCESS" else "Authentication Failed"}</h2>
    <p>{"Redirecting to application..." if status == "SUCCESS" else error}</p>
  </div>
  <script>
    (function() {{
      const targetOrigin = {target_origin_json};
      const payload = {payload_json};
      if (window.opener) {{
        window.opener.postMessage(payload, targetOrigin);
        setTimeout(function() {{ window.close(); }}, 800);
      }} else {{
        setTimeout(function() {{ window.location.href = "/#accounts"; }}, 1000);
      }}
    }})();
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=200 if status == "SUCCESS" else 400)


@router.get("/twitter/callback", response_class=HTMLResponse)
def twitter_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """OAuth 2.0 PKCE callback endpoint for X (Twitter)."""
    settings = get_settings()

    if error:
        logger.warning("Twitter OAuth callback error: %s (%s)", error, error_description)
        return _render_popup_callback_html("ERROR", "TWITTER", error=error_description or error)

    if not code or not state:
        logger.warning("Twitter OAuth callback missing code or state parameter.")
        return _render_popup_callback_html("ERROR", "TWITTER", error="Missing authorization code or state parameter.")

    try:
        # Atomically consume and validate state (single-use, context check)
        consumed_state = OAuthService.consume_oauth_state(
            db=db,
            state=state,
            expected_platform="TWITTER",
            expected_redirect_uri=settings.X_REDIRECT_URI,
        )

        # Exchange authorization code + PKCE verifier for tokens
        token_data = TwitterOAuthService.exchange_code_for_token(
            code=code,
            code_verifier=consumed_state.code_verifier or "",
            redirect_uri=settings.X_REDIRECT_URI,
        )

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 7200)

        if not access_token:
            return _render_popup_callback_html("ERROR", "TWITTER", error="No access token received from Twitter.")

        # Calculate token expiration
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Retrieve user profile
        profile = TwitterOAuthService.fetch_user_profile(access_token)
        account_name = profile.get("username") or "twitter_user"
        account_id = profile.get("account_id") or "tw_" + state[:8]

        # Upsert account with encrypted tokens
        OAuthService.upsert_social_account(
            db=db,
            platform=PlatformType.TWITTER,
            account_name=account_name,
            account_id=account_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
        )

        # Create activity log
        db.add(ActivityLog(
            action="ACCOUNT_CONNECTED",
            details=f"Connected X (Twitter) account @{account_name}",
            actor="User",
        ))
        db.commit()

        logger.info("Successfully connected Twitter account @%s", account_name)
        return _render_popup_callback_html("SUCCESS", "TWITTER", account_name=account_name)

    except HTTPException as http_exc:
        logger.warning("HTTP error in Twitter callback: %s", http_exc.detail)
        return _render_popup_callback_html("ERROR", "TWITTER", error=str(http_exc.detail))
    except Exception as exc:
        logger.exception("Unexpected error in Twitter callback: %s", exc)
        return _render_popup_callback_html("ERROR", "TWITTER", error="An internal error occurred during authentication.")


@router.post("/twitter/disconnect")
def twitter_disconnect(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Disconnects X (Twitter) account, revokes and wipes tokens, and logs the action."""
    account = db.query(SocialAccount).filter(SocialAccount.platform == PlatformType.TWITTER).first()
    if not account or not account.is_active:
        return {"success": True, "message": "Account was already disconnected."}

    # Best-effort token revocation
    if account.encrypted_access_token:
        from backend.app.auth.security import token_security
        raw_token = token_security.decrypt(account.encrypted_access_token)
        if raw_token:
            TwitterOAuthService.revoke_token(raw_token, token_type_hint="access_token")

    # Wipe and deactivate
    OAuthService.disconnect_social_account(db, PlatformType.TWITTER)

    # Log action
    db.add(ActivityLog(
        action="ACCOUNT_DISCONNECTED",
        details="Disconnected X (Twitter) account",
        actor="User",
    ))
    db.commit()

    return {"success": True, "message": "X (Twitter) account disconnected successfully."}
 
 
@router.get("/linkedin/authorize")
def linkedin_authorize(db: Session = Depends(get_db)) -> Dict[str, str]:
    """Generates state and returns the LinkedIn OAuth 2.0 authorization URL."""
    settings = get_settings()

    state_rec = OAuthService.create_oauth_state(
        db=db,
        platform="LINKEDIN",
        code_verifier=None,
        redirect_uri=settings.LINKEDIN_REDIRECT_URI,
        ttl_seconds=600,
    )

    auth_url = LinkedInOAuthService.build_authorization_url(
        state=state_rec.state,
        redirect_uri=settings.LINKEDIN_REDIRECT_URI,
    )

    return {
        "authorization_url": auth_url,
        "state": state_rec.state,
    }


@router.get("/linkedin/callback", response_class=HTMLResponse)
def linkedin_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """OAuth 2.0 callback endpoint for LinkedIn."""
    settings = get_settings()

    if error:
        logger.warning("LinkedIn OAuth callback error: %s (%s)", error, error_description)
        return _render_popup_callback_html("ERROR", "LINKEDIN", error=error_description or error)

    if not code or not state:
        logger.warning("LinkedIn OAuth callback missing code or state parameter.")
        return _render_popup_callback_html("ERROR", "LINKEDIN", error="Missing authorization code or state parameter.")

    try:
        # Atomically consume and validate state (single-use, context check)
        OAuthService.consume_oauth_state(
            db=db,
            state=state,
            expected_platform="LINKEDIN",
            expected_redirect_uri=settings.LINKEDIN_REDIRECT_URI,
        )

        # Exchange authorization code for token
        token_data = LinkedInOAuthService.exchange_code_for_token(
            code=code,
            redirect_uri=settings.LINKEDIN_REDIRECT_URI,
        )

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 5184000)  # Standard LinkedIn 60 days

        if not access_token:
            return _render_popup_callback_html("ERROR", "LINKEDIN", error="No access token received from LinkedIn.")

        # Calculate token expiration
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Retrieve user profile via OpenID Connect userinfo endpoint
        profile = LinkedInOAuthService.fetch_user_profile(access_token)
        account_name = profile.get("username") or "LinkedIn Member"
        account_id = profile.get("account_id") or "li_" + state[:8]

        # Upsert account with encrypted tokens
        OAuthService.upsert_social_account(
            db=db,
            platform=PlatformType.LINKEDIN,
            account_name=account_name,
            account_id=account_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
        )

        # Create activity log
        db.add(ActivityLog(
            action="ACCOUNT_CONNECTED",
            details=f"Connected LinkedIn account {account_name}",
            actor="User",
        ))
        db.commit()

        logger.info("Successfully connected LinkedIn account %s", account_name)
        return _render_popup_callback_html("SUCCESS", "LINKEDIN", account_name=account_name)

    except HTTPException as http_exc:
        logger.warning("HTTP error in LinkedIn callback: %s", http_exc.detail)
        return _render_popup_callback_html("ERROR", "LINKEDIN", error=str(http_exc.detail))
    except Exception as exc:
        logger.exception("Unexpected error in LinkedIn callback: %s", exc)
        return _render_popup_callback_html("ERROR", "LINKEDIN", error="An internal error occurred during authentication.")


@router.post("/linkedin/disconnect")
def linkedin_disconnect(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Disconnects LinkedIn account, wipes stored encrypted tokens, and logs the action."""
    account = db.query(SocialAccount).filter(SocialAccount.platform == PlatformType.LINKEDIN).first()
    if not account or not account.is_active:
        return {"success": True, "message": "Account was already disconnected."}

    OAuthService.disconnect_social_account(db, PlatformType.LINKEDIN)

    db.add(ActivityLog(
        action="ACCOUNT_DISCONNECTED",
        details="Disconnected LinkedIn account",
        actor="User",
    ))
    db.commit()

    return {"success": True, "message": "LinkedIn account disconnected successfully."}
 
 
@router.get("/facebook/authorize")
def facebook_authorize(db: Session = Depends(get_db)) -> Dict[str, str]:
    """Generates state and returns the Meta Facebook Page OAuth 2.0 authorization URL."""
    settings = get_settings()

    state_rec = OAuthService.create_oauth_state(
        db=db,
        platform="META_FACEBOOK",
        code_verifier=None,
        redirect_uri=settings.META_REDIRECT_URI,
        ttl_seconds=600,
    )

    auth_url = FacebookOAuthService.build_authorization_url(
        state=state_rec.state,
        redirect_uri=settings.META_REDIRECT_URI,
    )

    return {
        "authorization_url": auth_url,
        "state": state_rec.state,
    }


@router.get("/facebook/callback", response_class=HTMLResponse)
def facebook_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """OAuth 2.0 callback endpoint for Meta Facebook Pages."""
    settings = get_settings()

    if error:
        logger.warning("Facebook OAuth callback error: %s (%s)", error, error_description)
        return _render_popup_callback_html("ERROR", "META_FACEBOOK", error=error_description or error)

    if not code or not state:
        logger.warning("Facebook OAuth callback missing code or state parameter.")
        return _render_popup_callback_html("ERROR", "META_FACEBOOK", error="Missing authorization code or state parameter.")

    try:
        # Atomically consume and validate state (single-use, context check)
        OAuthService.consume_oauth_state(
            db=db,
            state=state,
            expected_platform="META_FACEBOOK",
            expected_redirect_uri=settings.META_REDIRECT_URI,
        )

        # 1. Exchange authorization code for short-lived user token
        user_token_data = FacebookOAuthService.exchange_code_for_user_token(
            code=code,
            redirect_uri=settings.META_REDIRECT_URI,
        )
        short_lived_token = user_token_data.get("access_token")
        if not short_lived_token:
            return _render_popup_callback_html("ERROR", "META_FACEBOOK", error="No user access token received from Meta.")

        # 2. Upgrade to long-lived user token (60 days)
        long_lived_data = FacebookOAuthService.exchange_for_long_lived_user_token(short_lived_token)
        user_access_token = long_lived_data.get("access_token") or short_lived_token

        # 3. Fetch managed Facebook Pages with Page Access Tokens
        pages = FacebookOAuthService.fetch_managed_pages(user_access_token)
        if not pages:
            logger.warning("Meta user authenticated successfully but has no managed Facebook Pages.")
            return _render_popup_callback_html(
                "ERROR",
                "META_FACEBOOK",
                error="No managed Facebook Pages found. You must be an admin of at least one Facebook Page."
            )

        # Select primary managed page (first available with CREATE_CONTENT or MANAGE task, or first page)
        selected_page = pages[0]
        page_id = str(selected_page.get("id"))
        page_name = selected_page.get("name") or f"Facebook Page {page_id}"
        page_access_token = selected_page.get("access_token")

        if not page_access_token:
            return _render_popup_callback_html(
                "ERROR",
                "META_FACEBOOK",
                error=f"No Page Access Token granted for '{page_name}'. Please ensure page management permissions are granted."
            )

        # Page access tokens from long-lived user tokens have no expiration (or 60-day expiry)
        token_expires_at = datetime.now(timezone.utc) + timedelta(days=60)

        # 4. Upsert account with encrypted Page Access Token
        OAuthService.upsert_social_account(
            db=db,
            platform=PlatformType.META_FACEBOOK,
            account_name=page_name,
            account_id=page_id,
            access_token=page_access_token,
            refresh_token=user_access_token,  # Keep user token as refresh token for re-generating page tokens
            token_expires_at=token_expires_at,
        )

        # Create activity log
        db.add(ActivityLog(
            action="ACCOUNT_CONNECTED",
            details=f"Connected Facebook Page '{page_name}' (ID: {page_id})",
            actor="User",
        ))
        db.commit()

        logger.info("Successfully connected Facebook Page '%s' (%s)", page_name, page_id)
        return _render_popup_callback_html("SUCCESS", "META_FACEBOOK", account_name=page_name)

    except HTTPException as http_exc:
        logger.warning("HTTP error in Facebook callback: %s", http_exc.detail)
        return _render_popup_callback_html("ERROR", "META_FACEBOOK", error=str(http_exc.detail))
    except Exception as exc:
        logger.exception("Unexpected error in Facebook callback: %s", exc)
        return _render_popup_callback_html("ERROR", "META_FACEBOOK", error="An internal error occurred during authentication.")


@router.post("/facebook/disconnect")
def facebook_disconnect(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Disconnects Facebook Page, wipes stored encrypted Page tokens, and logs the action."""
    account = db.query(SocialAccount).filter(SocialAccount.platform == PlatformType.META_FACEBOOK).first()
    if not account or not account.is_active:
        return {"success": True, "message": "Account was already disconnected."}

    OAuthService.disconnect_social_account(db, PlatformType.META_FACEBOOK)

    db.add(ActivityLog(
        action="ACCOUNT_DISCONNECTED",
        details="Disconnected Facebook Page",
        actor="User",
    ))
    db.commit()

    return {"success": True, "message": "Facebook Page disconnected successfully."}
 
 
@router.get("/instagram/authorize")
def instagram_authorize(db: Session = Depends(get_db)) -> Dict[str, str]:
    """Generates state and returns the Meta Instagram Business OAuth 2.0 authorization URL."""
    settings = get_settings()

    state_rec = OAuthService.create_oauth_state(
        db=db,
        platform="META_INSTAGRAM",
        code_verifier=None,
        redirect_uri=settings.INSTAGRAM_REDIRECT_URI,
        ttl_seconds=600,
    )

    auth_url = InstagramOAuthService.build_authorization_url(
        state=state_rec.state,
        redirect_uri=settings.INSTAGRAM_REDIRECT_URI,
    )

    return {
        "authorization_url": auth_url,
        "state": state_rec.state,
    }


@router.get("/instagram/callback", response_class=HTMLResponse)
def instagram_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """OAuth 2.0 callback endpoint for Meta Instagram Business."""
    settings = get_settings()

    if error:
        logger.warning("Instagram OAuth callback error: %s (%s)", error, error_description)
        return _render_popup_callback_html("ERROR", "META_INSTAGRAM", error=error_description or error)

    if not code or not state:
        logger.warning("Instagram OAuth callback missing code or state parameter.")
        return _render_popup_callback_html("ERROR", "META_INSTAGRAM", error="Missing authorization code or state parameter.")

    try:
        # Atomically consume and validate state (single-use, context check)
        OAuthService.consume_oauth_state(
            db=db,
            state=state,
            expected_platform="META_INSTAGRAM",
            expected_redirect_uri=settings.INSTAGRAM_REDIRECT_URI,
        )

        # 1. Exchange authorization code for user token
        user_token_data = FacebookOAuthService.exchange_code_for_user_token(
            code=code,
            redirect_uri=settings.INSTAGRAM_REDIRECT_URI,
        )
        short_lived_token = user_token_data.get("access_token")
        if not short_lived_token:
            return _render_popup_callback_html("ERROR", "META_INSTAGRAM", error="No user access token received from Meta.")

        # 2. Upgrade to long-lived user token (60 days)
        long_lived_data = FacebookOAuthService.exchange_for_long_lived_user_token(short_lived_token)
        user_access_token = long_lived_data.get("access_token") or short_lived_token

        # 3. Fetch managed Facebook Pages
        pages = FacebookOAuthService.fetch_managed_pages(user_access_token)
        if not pages:
            logger.warning("User authenticated successfully but has no managed Facebook Pages with linked Instagram accounts.")
            return _render_popup_callback_html(
                "ERROR",
                "META_INSTAGRAM",
                error="No managed Facebook Pages found. An Instagram Business account must be linked to a Facebook Page."
            )

        # 4. Search across managed pages for a linked Instagram Business Account
        discovered_ig = None
        selected_page = None
        for page in pages:
            page_id = page.get("id")
            page_token = page.get("access_token")
            if not page_id or not page_token:
                continue
            ig_data = InstagramOAuthService.fetch_linked_instagram_account(page_id, page_token)
            if ig_data:
                discovered_ig = ig_data
                selected_page = page
                break

        if not discovered_ig or not selected_page:
            logger.warning("No linked Instagram Business Account found across managed Facebook Pages.")
            return _render_popup_callback_html(
                "ERROR",
                "META_INSTAGRAM",
                error="No linked Instagram Business account found. Ensure your Instagram Professional account is linked to your Facebook Page in Meta Business Suite."
            )

        ig_user_id = discovered_ig["id"]
        ig_username = discovered_ig.get("username") or "instagram_business"
        account_name = f"@{ig_username}"
        page_access_token = selected_page["access_token"]

        # Page access tokens from long-lived user tokens last 60 days
        token_expires_at = datetime.now(timezone.utc) + timedelta(days=60)

        # 5. Upsert account with encrypted Page Access Token and Instagram User ID
        OAuthService.upsert_social_account(
            db=db,
            platform=PlatformType.META_INSTAGRAM,
            account_name=account_name,
            account_id=ig_user_id,
            access_token=page_access_token,
            refresh_token=user_access_token,
            token_expires_at=token_expires_at,
        )

        # Create activity log
        db.add(ActivityLog(
            action="ACCOUNT_CONNECTED",
            details=f"Connected Instagram Business account '{account_name}' (ID: {ig_user_id})",
            actor="User",
        ))
        db.commit()

        logger.info("Successfully connected Instagram Business account '%s' (%s)", account_name, ig_user_id)
        return _render_popup_callback_html("SUCCESS", "META_INSTAGRAM", account_name=account_name)

    except HTTPException as http_exc:
        logger.warning("HTTP error in Instagram callback: %s", http_exc.detail)
        return _render_popup_callback_html("ERROR", "META_INSTAGRAM", error=str(http_exc.detail))
    except Exception as exc:
        logger.exception("Unexpected error in Instagram callback: %s", exc)
        return _render_popup_callback_html("ERROR", "META_INSTAGRAM", error="An internal error occurred during authentication.")


@router.post("/instagram/disconnect")
def instagram_disconnect(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Disconnects Instagram Business account, wipes stored encrypted tokens, and logs the action."""
    account = db.query(SocialAccount).filter(SocialAccount.platform == PlatformType.META_INSTAGRAM).first()
    if not account or not account.is_active:
        return {"success": True, "message": "Account was already disconnected."}

    OAuthService.disconnect_social_account(db, PlatformType.META_INSTAGRAM)

    db.add(ActivityLog(
        action="ACCOUNT_DISCONNECTED",
        details="Disconnected Instagram Business account",
        actor="User",
    ))
    db.commit()

    return {"success": True, "message": "Instagram Business account disconnected successfully."}
