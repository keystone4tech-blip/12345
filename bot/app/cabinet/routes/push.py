"""Web Push settings and subscription routes for cabinet."""

from datetime import datetime, UTC
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, PushSubscription
from app.config import settings

from ..dependencies import get_cabinet_db, get_current_cabinet_user

logger = structlog.get_logger(__name__)

router = APIRouter(prefix='/push', tags=['Cabinet Web Push'])


# ============ Schemas ============

class VapidKeyResponse(BaseModel):
    """VAPID public key response."""
    public_key: str


class PushKeys(BaseModel):
    """Encryption keys for Web Push subscription."""
    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    """Create or update a push subscription."""
    endpoint: str
    keys: PushKeys


class UnsubscribeRequest(BaseModel):
    """Unsubscribe request containing the endpoint."""
    endpoint: str


# ============ Routes ============

@router.get('/vapid-key', response_model=VapidKeyResponse)
async def get_vapid_key():
    """Get VAPID public key for subscribing to push notifications."""
    if not settings.VAPID_PUBLIC_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="VAPID keys are not configured or generated on the server."
        )
    return VapidKeyResponse(public_key=settings.VAPID_PUBLIC_KEY)


@router.post('/subscribe')
async def subscribe_push(
    request: PushSubscriptionCreate,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Save or update push subscription for current user."""
    endpoint = request.endpoint.strip()
    p256dh = request.keys.p256dh.strip()
    auth = request.keys.auth.strip()

    if not endpoint or not p256dh or not auth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid subscription format. Missing endpoint, p256dh or auth keys."
        )

    try:
        # Check if subscription already exists for this endpoint
        stmt = select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # If it exists, update key info and transfer ownership to current user if needed
            existing.user_id = user.id
            existing.p256dh = p256dh
            existing.auth = auth
            existing.updated_at = datetime.now(UTC)
            logger.info("Updated existing push subscription", user_id=user.id, endpoint=endpoint[:30])
        else:
            # Create a brand new subscription
            new_sub = PushSubscription(
                user_id=user.id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC)
            )
            db.add(new_sub)
            logger.info("Registered new push subscription", user_id=user.id, endpoint=endpoint[:30])

        await db.commit()
        return {"success": True, "message": "Successfully subscribed to push notifications."}

    except Exception as e:
        await db.rollback()
        logger.error("Failed to subscribe to push notifications", user_id=user.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while saving the push subscription."
        )


@router.post('/unsubscribe')
async def unsubscribe_push(
    request: UnsubscribeRequest,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Delete a push subscription."""
    endpoint = request.endpoint.strip()

    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing endpoint parameter."
        )

    try:
        # Delete only subscriptions belonging to the current user
        stmt = delete(PushSubscription).where(
            (PushSubscription.endpoint == endpoint) & (PushSubscription.user_id == user.id)
        )
        result = await db.execute(stmt)
        
        if result.rowcount > 0:
            await db.commit()
            logger.info("Removed push subscription", user_id=user.id, endpoint=endpoint[:30])
            return {"success": True, "message": "Successfully unsubscribed."}
        else:
            return {"success": True, "message": "No active subscription found for this endpoint."}

    except Exception as e:
        await db.rollback()
        logger.error("Failed to unsubscribe from push notifications", user_id=user.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the push subscription."
        )
