"""Gift system schemas for cabinet."""

from datetime import datetime
from pydantic import BaseModel, Field


class GiftTariffPeriod(BaseModel):
    """Period and price info for a gift tariff."""
    days: int
    price_kopeks: int
    price_label: str
    original_price_kopeks: int | None = None
    discount_percent: int | None = None


class GiftTariff(BaseModel):
    """Tariff info for gifting."""
    id: int
    name: str
    description: str | None = None
    traffic_limit_gb: int
    device_limit: int
    periods: list[GiftTariffPeriod]


class GiftPaymentMethodSubOption(BaseModel):
    """Sub-option for a payment method (e.g. specific crypto currency)."""
    id: str
    name: str


class GiftPaymentMethod(BaseModel):
    """Payment method info for gifts."""
    method_id: str
    display_name: str
    description: str | None = None
    icon_url: str | None = None
    min_amount_kopeks: int | None = None
    max_amount_kopeks: int | None = None
    sub_options: list[GiftPaymentMethodSubOption] | None = None


class GiftConfig(BaseModel):
    """Global configuration for the gift system."""
    is_enabled: bool
    tariffs: list[GiftTariff]
    payment_methods: list[GiftPaymentMethod]
    balance_kopeks: int
    currency_symbol: str
    promo_group_name: str | None = None
    active_discount_percent: int | None = None
    active_discount_expires_at: datetime | None = None


class GiftPurchaseRequest(BaseModel):
    """Request to purchase a gift."""
    tariff_id: int
    period_days: int
    recipient_type: str | None = "telegram" # 'email' | 'telegram'
    recipient_value: str | None = None
    gift_message: str | None = None
    payment_mode: str # 'balance' | 'gateway'
    payment_method: str | None = None


class GiftPurchaseResponse(BaseModel):
    """Response after creating a gift purchase."""
    status: str # 'ok' | 'created' | 'paid'
    purchase_token: str
    payment_url: str | None = None
    warning: str | None = None


class GiftPurchaseStatus(BaseModel):
    """Current status of a gift purchase."""
    status: str
    is_gift: bool
    is_code_only: bool
    purchase_token: str | None = None
    recipient_contact_value: str | None = None
    gift_message: str | None = None
    tariff_name: str | None = None
    period_days: int | None = None
    warning: str | None = None


class PendingGift(BaseModel):
    """Info about a gift waiting to be activated."""
    token: str
    tariff_name: str | None = None
    period_days: int
    gift_message: str | None = None
    sender_display: str | None = None
    created_at: datetime | None = None


class SentGift(BaseModel):
    """Info about a gift sent by the user."""
    token: str
    tariff_name: str | None = None
    period_days: int
    device_limit: int
    status: str
    gift_recipient_value: str | None = None
    gift_message: str | None = None
    activated_by_username: str | None = None
    created_at: datetime | None = None


class ReceivedGift(BaseModel):
    """Info about a gift received by the user."""
    token: str
    tariff_name: str | None = None
    period_days: int
    device_limit: int
    status: str
    sender_display: str | None = None
    gift_message: str | None = None
    created_at: datetime | None = None


class ActivateGiftResponse(BaseModel):
    """Response after activating a gift code."""
    status: str
    tariff_name: str | None = None
    period_days: int | None = None


class ActivateGiftRequest(BaseModel):
    """Request to activate a gift code."""
    code: str


class SendGiftToUserRequest(BaseModel):
    """Request to send a gift directly to a user by Telegram username."""
    token: str
    username: str


class SendGiftToUserResponse(BaseModel):
    """Response after sending a gift directly to a user by Telegram username."""
    status: str
    message: str

