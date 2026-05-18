"""Authentication schemas for cabinet."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class TelegramAuthRequest(BaseModel):
    """Request for Telegram WebApp initData authentication."""

    init_data: str = Field(..., description='Telegram WebApp initData string')
    campaign_slug: str | None = Field(
        None, min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$', description='Campaign slug from web link'
    )
    referral_code: str | None = Field(None, max_length=32, description='Referral code of inviter')


class TelegramWidgetAuthRequest(BaseModel):
    """Request for Telegram Login Widget authentication."""

    id: int = Field(..., description='Telegram user ID')
    first_name: str = Field(..., description="User's first name")
    last_name: str | None = Field(None, description="User's last name")
    username: str | None = Field(None, description="User's username")
    photo_url: str | None = Field(None, description="User's photo URL")
    auth_date: int = Field(..., description='Unix timestamp of authentication')
    hash: str = Field(..., description='Authentication hash')
    campaign_slug: str | None = Field(
        None, min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$', description='Campaign slug from web link'
    )
    referral_code: str | None = Field(None, max_length=32, description='Referral code of inviter')


class EmailRegisterRequest(BaseModel):
    """Request to register/link email to existing Telegram account."""

    email: EmailStr = Field(..., description='Email address')
    password: str = Field(..., min_length=8, max_length=128, description='Password (min 8 chars)')


class EmailVerifyRequest(BaseModel):
    """Request to verify email with token."""

    token: str = Field(..., description='Email verification token')
    campaign_slug: str | None = Field(
        None, min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$', description='Campaign slug from web link'
    )


class EmailLoginRequest(BaseModel):
    """Request to login with email and password."""

    email: EmailStr = Field(..., description='Email address')
    password: str = Field(..., description='Password')
    campaign_slug: str | None = Field(
        None, min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$', description='Campaign slug from web link'
    )


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token."""

    refresh_token: str = Field(..., description='Refresh token')


class AutoLoginRequest(BaseModel):
    """Request for automatic login via token."""

    token: str = Field(..., description='Auto-login token')


class PasswordForgotRequest(BaseModel):
    """Request to initiate password reset."""

    email: EmailStr = Field(..., description='Email address')


class PasswordResetRequest(BaseModel):
    """Request to reset password with token."""

    token: str = Field(..., description='Password reset token')
    password: str = Field(..., min_length=8, max_length=128, description='New password (min 8 chars)')


class TokenResponse(BaseModel):
    """Token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = 'bearer'
    expires_in: int = Field(..., description='Access token expiration in seconds')


class UserResponse(BaseModel):
    """User data response."""

    id: int
    telegram_id: int | None = None  # Nullable для email-only пользователей
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    email_verified: bool = False
    balance_kopeks: int = 0
    balance_rubles: float = 0.0
    referral_code: str | None = None
    language: str = 'ru'
    created_at: datetime
    auth_type: str = 'telegram'  # "telegram" или "email"

    class Config:
        from_attributes = True


class EmailRegisterStandaloneRequest(BaseModel):
    """Request to register new account with email (no Telegram required)."""

    email: EmailStr = Field(..., description='Email address')
    password: str = Field(..., min_length=8, max_length=128, description='Password (min 8 chars)')
    first_name: str | None = Field(None, max_length=64, description='First name')
    language: str = Field('ru', description='Preferred language')
    referral_code: str | None = Field(None, max_length=32, description='Referral code of inviter')


class CampaignBonusInfo(BaseModel):
    """Info about campaign bonus applied during auth."""

    campaign_name: str
    bonus_type: str
    balance_kopeks: int = 0
    subscription_days: int | None = None
    tariff_name: str | None = None


class AuthResponse(BaseModel):
    """Full authentication response with tokens and user."""

    access_token: str
    refresh_token: str
    token_type: str = 'bearer'
    expires_in: int
    user: UserResponse
    campaign_bonus: CampaignBonusInfo | None = None


class RegisterResponse(BaseModel):
    """Response for email registration (before verification)."""

    message: str = Field(..., description='Success message')
    email: str = Field(..., description='Email address to verify')
    requires_verification: bool = Field(True, description='Whether email verification is required')


class EmailChangeRequest(BaseModel):
    """Request to initiate email change."""

    new_email: EmailStr = Field(..., description='New email address')


class EmailChangeVerifyRequest(BaseModel):
    """Request to verify email change with code."""

    code: str = Field(..., min_length=6, max_length=6, description='6-digit verification code')


class EmailChangeResponse(BaseModel):
    """Response for email change initiation."""

    message: str = Field(..., description='Success message')
    new_email: str = Field(..., description='New email address pending verification')
    expires_in_minutes: int = Field(..., description='Code expiration time in minutes')


class LinkedProvider(BaseModel):
    """Информация о привязанном способе авторизации (Telegram, Email, OAuth)."""

    provider: str = Field(..., description="Имя провайдера (telegram, email, google, yandex, discord, vk)")
    linked: bool = Field(..., description="Привязан ли данный провайдер к аккаунту")
    identifier: str | None = Field(None, description="Идентификатор провайдера (email, username или id)")


class LinkedProvidersResponse(BaseModel):
    """Ответ со списком всех привязанных и доступных провайдеров авторизации."""

    providers: list[LinkedProvider]


class LinkCallbackResponse(BaseModel):
    """Ответ на запрос привязки или отвязки аккаунта провайдера."""

    success: bool
    message: str | None = Field(None, description="Сообщение о результате операции")
    merge_required: bool = Field(False, description="Флаг необходимости слияния аккаунтов")
    merge_token: str | None = Field(None, description="Временный токен для слияния аккаунтов")


class ServerCompleteResponse(LinkCallbackResponse):
    """Ответ для подтверждения привязки со стороны внешнего браузера."""

    provider: str = Field(..., description="Имя провайдера авторизации")


# --- Схемы Слияния Аккаунтов (Account Merge) ---

class MergeSubscriptionPreview(BaseModel):
    """Превью информации о подписке перед слиянием аккаунтов."""

    status: str = Field(..., description="Статус подписки")
    is_trial: bool = Field(..., description="Является ли подписка пробной")
    end_date: str | None = Field(None, description="Дата окончания подписки (ISO string)")
    traffic_limit_gb: float = Field(..., description="Лимит трафика в ГБ")
    traffic_used_gb: float = Field(..., description="Использованный трафик в ГБ")
    device_limit: int = Field(..., description="Лимит устройств")
    tariff_name: str | None = Field(None, description="Название текущего тарифа")
    autopay_enabled: bool = Field(..., description="Включено ли автопродление")


class MergeAccountPreview(BaseModel):
    """Превью информации об аккаунте пользователя перед слиянием."""

    id: int = Field(..., description="ID пользователя в системе")
    username: str | None = Field(None, description="Имя пользователя в Telegram")
    first_name: str | None = Field(None, description="Имя пользователя")
    email: str | None = Field(None, description="Электронная почта")
    auth_methods: list[str] = Field(..., description="Активные методы авторизации (telegram, email и т.д.)")
    balance_kopeks: int = Field(..., description="Баланс аккаунта в копейках")
    subscription: MergeSubscriptionPreview | None = Field(None, description="Информация о подписке")
    created_at: str | None = Field(None, description="Дата создания аккаунта (ISO string)")


class MergePreviewResponse(BaseModel):
    """Ответ с детальной информацией о первичном и вторичном аккаунтах для сравнения при слиянии."""

    primary: MergeAccountPreview = Field(..., description="Основной (текущий авторизованный) аккаунт")
    secondary: MergeAccountPreview = Field(..., description="Вторичный (привязываемый конфликтующий) аккаунт")
    expires_in_seconds: int = Field(..., description="Время жизни токена слияния в секундах")


class MergeRequest(BaseModel):
    """Запрос на подтверждение слияния аккаунтов."""

    keep_subscription_from: int = Field(..., description="ID пользователя, чью подписку нужно сохранить")


class MergeResponse(BaseModel):
    """Ответ на успешное слияние аккаунтов."""

    success: bool = Field(..., description="Флаг успешности операции")
    access_token: str | None = Field(None, description="Новый JWT access токен")
    refresh_token: str | None = Field(None, description="Новый JWT refresh токен")
    user: UserResponse | None = Field(None, description="Данные объединенного пользователя")

