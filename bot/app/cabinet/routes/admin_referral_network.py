"""Роутер администратора для управления и визуализации реферальной сети MozhnoVPN."""

import asyncio
from datetime import datetime, UTC
from typing import Literal, List, Dict, Any, Set
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    User,
    AdvertisingCampaign,
    AdvertisingCampaignRegistration,
    ReferralEarning,
    Transaction,
    Subscription,
    Tariff
)
from ..dependencies import get_cabinet_db, require_permission
from app.utils.formatters import strip_telegram_tags

logger = structlog.get_logger(__name__)

router = APIRouter(prefix='/admin/referral-network', tags=['Cabinet Admin Referral Network'])

# ==================== Pydantic Схемы ====================

class CampaignOption(BaseModel):
    """Опция рекламной кампании для ScopeSelector."""
    id: int
    name: str
    start_parameter: str
    is_active: bool
    direct_users: int

class PartnerOption(BaseModel):
    """Опция партнера для ScopeSelector."""
    id: int
    display_name: str
    username: str | None
    campaign_count: int

class ScopeOptionsData(BaseModel):
    """Данные для селектора области видимости (ScopeSelector)."""
    campaigns: List[CampaignOption]
    partners: List[PartnerOption]

class NetworkUserNode(BaseModel):
    """Узел пользователя на графе реферальной сети."""
    id: int
    tg_id: int | None
    username: str | None
    email: str | None
    display_name: str
    is_partner: bool
    referrer_id: int | None
    campaign_id: int | None
    direct_referrals: int
    total_branch_users: int
    branch_revenue_kopeks: int
    personal_revenue_kopeks: int
    personal_spent_kopeks: int
    subscription_name: str | None
    subscription_end: str | None
    subscription_status: str | None
    registered_at: str | None

class NetworkCampaignNode(BaseModel):
    """Узел рекламной кампании на графе реферальной сети."""
    id: int
    name: str
    start_parameter: str
    is_active: bool
    direct_users: int
    total_network_users: int
    total_revenue_kopeks: int
    conversion_rate: float
    avg_check_kopeks: float
    top_referrers: List[Dict[str, Any]]

class NetworkEdge(BaseModel):
    """Ребро (связь) в графе реферальной сети."""
    source: str  # Формат: 'user:{id}' или 'campaign:{id}'
    target: str  # Формат: 'user:{id}' или 'campaign:{id}'
    type: Literal['referral', 'campaign', 'partner_campaign']

class NetworkGraphData(BaseModel):
    """Полные данные графа реферальной сети."""
    users: List[NetworkUserNode]
    campaigns: List[NetworkCampaignNode]
    edges: List[NetworkEdge]
    total_users: int
    total_referrers: int
    total_campaigns: int
    total_earnings_kopeks: int
    total_subscription_revenue_kopeks: int

class NetworkUserDetail(BaseModel):
    """Детальная информация о пользователе для боковой панели."""
    id: int
    tg_id: int | None
    username: str | None
    email: str | None
    display_name: str
    is_partner: bool
    referrer_id: int | None
    referrer_display_name: str | None
    campaign_id: int | None
    campaign_name: str | None
    direct_referrals: int
    total_branch_users: int
    branch_revenue_kopeks: int
    personal_revenue_kopeks: int
    personal_spent_kopeks: int
    subscription_name: str | None
    subscription_end: str | None
    subscription_status: str | None
    registered_at: str | None

class NetworkCampaignDetail(BaseModel):
    """Детальная информация о рекламной кампании для боковой панели."""
    id: int
    name: str
    start_parameter: str
    is_active: bool
    direct_users: int
    total_network_users: int
    total_revenue_kopeks: int
    conversion_rate: float
    avg_check_kopeks: float
    top_referrers: List[Dict[str, Any]]

class NetworkSearchResult(BaseModel):
    """Результаты живого поиска по реферальной сети."""
    users: List[NetworkUserNode]
    campaigns: List[NetworkCampaignNode]

# ==================== Вспомогательные функции бэкенда ====================

def _get_display_name(user: User) -> str:
    """Определяет красивое отображаемое имя для пользователя."""
    if user.first_name:
        parts = [user.first_name]
        if user.last_name:
            parts.append(user.last_name)
        return " ".join(parts)
    if user.username:
        return f"@{user.username}"
    if user.email:
        return user.email
    if user.telegram_id:
        return f"User {user.telegram_id}"
    return f"User #{user.id}"

def _determine_subscription_status(sub: Subscription | None) -> str | None:
    """Определяет статус подписки пользователя."""
    if not sub:
        return None
    
    now = datetime.now(UTC)
    is_active = sub.status == 'active' and (sub.end_date is None or sub.end_date.replace(tzinfo=UTC) > now)
    
    if is_active:
        return 'trial_active' if sub.is_trial else 'paid_active'
    else:
        return 'trial_expired' if sub.is_trial else 'paid_expired'

async def _calculate_branch_stats(db: AsyncSession, user_id: int) -> tuple[int, int]:
    """Рекурсивно вычисляет количество пользователей и выручку всей реферальной ветки."""
    # Используем рекурсивное CTE (Common Table Expression) в PostgreSQL для быстрого обхода дерева
    query = f"""
    WITH RECURSIVE referral_tree AS (
        -- Базовый случай: прямые рефералы пользователя
        SELECT id, referred_by_id
        FROM users
        WHERE referred_by_id = :user_id
        
        UNION ALL
        
        -- Рекурсивный случай: рефералы следующего уровня
        SELECT u.id, u.referred_by_id
        FROM users u
        JOIN referral_tree rt ON u.referred_by_id = rt.id
    )
    SELECT 
        COUNT(rt.id) as branch_count,
        COALESCE(
            (SELECT SUM(ABS(t.amount_kopeks))
             FROM transactions t
             WHERE t.user_id IN (SELECT id FROM referral_tree)
               AND t.type IN ('subscription_payment', 'deposit')
               AND t.is_completed = true),
            0
        ) as branch_revenue
    FROM referral_tree rt;
    """
    
    try:
        result = await db.execute(func.text(query), {"user_id": user_id})
        row = result.fetchone()
        if row:
            return int(row[0] or 0), int(row[1] or 0)
    except Exception as e:
        logger.error("Ошибка при вычислении ветки рефералов через CTE", user_id=user_id, error=e)
    
    return 0, 0

async def _get_personal_revenue(db: AsyncSession, user_id: int) -> int:
    """Вычисляет общие затраты конкретного пользователя на подписки и пополнения."""
    query = select(func.coalesce(func.sum(func.abs(Transaction.amount_kopeks)), 0)).where(
        Transaction.user_id == user_id,
        Transaction.type.in_(['subscription_payment', 'deposit']),
        Transaction.is_completed.is_(True)
    )
    result = await db.execute(query)
    return int(result.scalar() or 0)

# ==================== Эндпоинты API ====================

@router.get('/scope-options', response_model=ScopeOptionsData)
async def get_scope_options(
    admin: User = Depends(require_permission('partners:read')),
    db: AsyncSession = Depends(get_cabinet_db)
):
    """Возвращает список рекламных кампаний и партнеров для ScopeSelector."""
    logger.info("Загрузка опций областей видимости для реферальной сети", admin_id=admin.id)
    
    # 1. Загрузка рекламных кампаний и количества их прямых регистраций
    campaigns_query = select(
        AdvertisingCampaign,
        func.count(AdvertisingCampaignRegistration.id).label('reg_count')
    ).outerjoin(
        AdvertisingCampaignRegistration,
        AdvertisingCampaignRegistration.campaign_id == AdvertisingCampaign.id
    ).group_by(
        AdvertisingCampaign.id
    ).order_by(
        desc(AdvertisingCampaign.is_active),
        AdvertisingCampaign.name
    )
    
    campaigns_res = await db.execute(campaigns_query)
    campaign_options = []
    for camp, reg_count in campaigns_res.all():
        campaign_options.append(
            CampaignOption(
                id=camp.id,
                name=camp.name,
                start_parameter=camp.start_parameter,
                is_active=camp.is_active,
                direct_users=reg_count or 0
            )
        )
        
    # 2. Загрузка партнеров (пользователей с одобренным статусом партнера)
    partners_query = select(
        User,
        func.count(AdvertisingCampaign.id).label('camp_count')
    ).outerjoin(
        AdvertisingCampaign,
        AdvertisingCampaign.partner_user_id == User.id
    ).where(
        User.partner_status == 'approved'
    ).group_by(
        User.id
    ).order_by(
        User.username
    )
    
    partners_res = await db.execute(partners_query)
    partner_options = []
    for partner, camp_count in partners_res.all():
        partner_options.append(
            PartnerOption(
                id=partner.id,
                display_name=_get_display_name(partner),
                username=partner.username,
                campaign_count=camp_count or 0
            )
        )
        
    return ScopeOptionsData(campaigns=campaign_options, partners=partner_options)


@router.get('/scoped', response_model=NetworkGraphData)
async def get_scoped_graph(
    campaign_ids: List[int] = Query(default=[]),
    partner_ids: List[int] = Query(default=[]),
    user_ids: List[int] = Query(default=[]),
    admin: User = Depends(require_permission('partners:read')),
    db: AsyncSession = Depends(get_cabinet_db)
):
    """Построение интерактивного графа реферальной сети на основе выбранных ID (фильтра области)."""
    logger.info(
        "Запрос графа реферальной сети",
        admin_id=admin.id,
        campaigns=campaign_ids,
        partners=partner_ids,
        users=user_ids
    )
    
    # Результирующие списки для графа
    users_nodes: Dict[int, User] = {}
    campaigns_nodes: Dict[int, AdvertisingCampaign] = {}
    edges: Set[tuple[str, str, str]] = set()
    
    # 1. Сценарий по умолчанию: пустые фильтры (загружаем превью)
    if not campaign_ids and not partner_ids and not user_ids:
        # Выбираем всех одобренных партнеров и рекламные кампании
        partners_q = select(User).where(User.partner_status == 'approved').limit(50)
        partners_res = await db.execute(partners_q)
        for partner in partners_res.scalars().all():
            users_nodes[partner.id] = partner
            
        campaigns_q = select(AdvertisingCampaign).limit(50)
        campaigns_res = await db.execute(campaigns_q)
        for camp in campaigns_res.scalars().all():
            campaigns_nodes[camp.id] = camp
            
        # Загружаем также рефереров, у которых больше всего прямых приглашений
        top_referrers_q = select(
            User, func.count(User.id).label('ref_count')
        ).where(
            User.referred_by_id.isnot(None)
        ).group_by(
            User.referred_by_id, User.id
        ).order_by(
            desc('ref_count')
        ).limit(30)
        
        top_res = await db.execute(top_referrers_q)
        for ref_user, _ in top_res.all():
            users_nodes[ref_user.id] = ref_user
            
    # 2. Сценарий с выбранной областью фильтрации
    else:
        # А. Загружаем кампании по ID
        if campaign_ids:
            camps_q = select(AdvertisingCampaign).where(AdvertisingCampaign.id.in_(campaign_ids))
            camps_res = await db.execute(camps_q)
            for camp in camps_res.scalars().all():
                campaigns_nodes[camp.id] = camp
                
        # Б. Загружаем партнеров по ID
        if partner_ids:
            parts_q = select(User).where(User.id.in_(partner_ids))
            parts_res = await db.execute(parts_q)
            for partner in parts_res.scalars().all():
                users_nodes[partner.id] = partner
                
        # В. Загружаем пользователей по ID
        if user_ids:
            usr_q = select(User).where(User.id.in_(user_ids))
            usr_res = await db.execute(usr_q)
            for usr in usr_res.scalars().all():
                users_nodes[usr.id] = usr
                
        # Г. Догружаем связанные сущности (прямые рефералы, регистрации кампаний и владельцев кампаний)
        # Получаем регистрации для выбранных кампаний
        if campaign_ids:
            regs_q = select(User).join(
                AdvertisingCampaignRegistration,
                AdvertisingCampaignRegistration.user_id == User.id
            ).where(
                AdvertisingCampaignRegistration.campaign_id.in_(campaign_ids)
            ).limit(100)
            regs_res = await db.execute(regs_q)
            for registered_user in regs_res.scalars().all():
                users_nodes[registered_user.id] = registered_user
                
        # Получаем кампании и рефералов для выбранных партнеров
        if partner_ids:
            # Кампании, принадлежащие партнеру
            partner_camps_q = select(AdvertisingCampaign).where(AdvertisingCampaign.partner_user_id.in_(partner_ids))
            partner_camps_res = await db.execute(partner_camps_q)
            for camp in partner_camps_res.scalars().all():
                campaigns_nodes[camp.id] = camp
                
            # Прямые рефералы партнера
            partner_refs_q = select(User).where(User.referred_by_id.in_(partner_ids)).limit(100)
            partner_refs_res = await db.execute(partner_refs_q)
            for ref_user in partner_refs_res.scalars().all():
                users_nodes[ref_user.id] = ref_user
                
        # Получаем прямых рефералов для выбранных пользователей
        if user_ids:
            refs_q = select(User).where(User.referred_by_id.in_(user_ids)).limit(100)
            refs_res = await db.execute(refs_q)
            for ref_user in refs_res.scalars().all():
                users_nodes[ref_user.id] = ref_user

    # 3. Замыкание графа (догрузка отсутствующих рефереров и кампаний, чтобы не было битых связей)
    missing_user_ids = set()
    missing_campaign_ids = set()
    
    # Сканируем связи, чтобы найти ID отсутствующих узлов в текущих коллекциях
    for user_id, user in list(users_nodes.items()):
        if user.referred_by_id and user.referred_by_id not in users_nodes:
            missing_user_ids.add(user.referred_by_id)
            
    # Загружаем регистрации пользователей в кампаниях, чтобы связать пользователей с кампаниями
    user_registrations: Dict[int, AdvertisingCampaignRegistration] = {}
    if users_nodes:
        regs_q = select(AdvertisingCampaignRegistration).where(
            AdvertisingCampaignRegistration.user_id.in_(list(users_nodes.keys()))
        )
        regs_res = await db.execute(regs_q)
        for reg in regs_res.scalars().all():
            user_registrations[reg.user_id] = reg
            if reg.campaign_id not in campaigns_nodes:
                missing_campaign_ids.add(reg.campaign_id)
                
    # Загружаем недостающие кампании
    if missing_campaign_ids:
        missing_c_q = select(AdvertisingCampaign).where(AdvertisingCampaign.id.in_(list(missing_campaign_ids)))
        missing_c_res = await db.execute(missing_c_q)
        for camp in missing_c_res.scalars().all():
            campaigns_nodes[camp.id] = camp
            
    # Догружаем недостающих рефереров (ограничимся 50 для безопасности)
    if missing_user_ids:
        missing_u_q = select(User).where(User.id.in_(list(missing_user_ids)[:50]))
        missing_u_res = await db.execute(missing_u_q)
        for missing_usr in missing_u_res.scalars().all():
            users_nodes[missing_usr.id] = missing_usr

    # 4. Сбор и построение ребер графа
    for user_id, user in users_nodes.items():
        # Связь: приглашение (Referral)
        if user.referred_by_id and user.referred_by_id in users_nodes:
            edges.add((f"user:{user.referred_by_id}", f"user:{user_id}", 'referral'))
            
        # Связь: регистрация в рекламной кампании (Campaign Registration)
        reg = user_registrations.get(user_id)
        if reg and reg.campaign_id in campaigns_nodes:
            edges.add((f"campaign:{reg.campaign_id}", f"user:{user_id}", 'campaign'))
            
    # Связь: привязка кампании к партнеру (Partner Campaign)
    for camp_id, camp in campaigns_nodes.items():
        if camp.partner_user_id and camp.partner_user_id in users_nodes:
            edges.add((f"user:{camp.partner_user_id}", f"campaign:{camp_id}", 'partner_campaign'))

    # 5. Сбор и вычисление статистики для узлов графа
    # Вытягиваем подписки для пользователей, чтобы отобразить названия подписок и статусы подписок
    user_subscriptions: Dict[int, Subscription] = {}
    if users_nodes:
        subs_q = select(Subscription).options(selectinload(Subscription.tariff)).where(
            Subscription.user_id.in_(list(users_nodes.keys())),
            Subscription.status == 'active'
        )
        subs_res = await db.execute(subs_q)
        for sub in subs_res.scalars().all():
            user_subscriptions[sub.user_id] = sub
            
    # Подсчет прямых рефералов для каждого пользователя в базе
    referral_counts: Dict[int, int] = {}
    if users_nodes:
        counts_q = select(User.referred_by_id, func.count(User.id)).where(
            User.referred_by_id.in_(list(users_nodes.keys()))
        ).group_by(User.referred_by_id)
        counts_res = await db.execute(counts_q)
        for ref_id, count in counts_res.all():
            if ref_id is not None:
                referral_counts[ref_id] = count

    # Собираем пользователей графа
    nodes_users_list: List[NetworkUserNode] = []
    total_earnings_accumulated = 0
    
    for user_id, user in users_nodes.items():
        sub = user_subscriptions.get(user_id)
        sub_name = strip_telegram_tags(sub.tariff.name) if sub and sub.tariff else ("Пробный" if sub and sub.is_trial else None)
        sub_status = _determine_subscription_status(sub)
        sub_end_iso = sub.end_date.isoformat() if sub and sub.end_date else None
        
        # Получаем выручку ветки и личные расходы
        branch_users_count, branch_revenue = await _calculate_branch_stats(db, user_id)
        personal_spent = await _get_personal_revenue(db, user_id)
        
        # Заработанная реферальная комиссия партнера
        earnings_q = select(func.coalesce(func.sum(ReferralEarning.amount_kopeks), 0)).where(
            ReferralEarning.user_id == user_id
        )
        earnings_res = await db.execute(earnings_q)
        personal_earnings = int(earnings_res.scalar() or 0)
        total_earnings_accumulated += personal_earnings
        
        reg = user_registrations.get(user_id)
        camp_id = reg.campaign_id if reg else None
        
        nodes_users_list.append(
            NetworkUserNode(
                id=user.id,
                tg_id=user.telegram_id,
                username=user.username,
                email=user.email,
                display_name=_get_display_name(user),
                is_partner=user.partner_status == 'approved',
                referrer_id=user.referred_by_id,
                campaign_id=camp_id,
                direct_referrals=referral_counts.get(user_id, 0),
                total_branch_users=branch_users_count,
                branch_revenue_kopeks=branch_revenue,
                personal_revenue_kopeks=personal_spent,
                personal_spent_kopeks=personal_spent,
                subscription_name=sub_name,
                subscription_end=sub_end_iso,
                subscription_status=sub_status,
                registered_at=user.created_at.isoformat() if user.created_at else None
            )
        )

    # Собираем рекламные кампании графа
    nodes_campaigns_list: List[NetworkCampaignNode] = []
    
    for camp_id, camp in campaigns_nodes.items():
        # Считаем количество переходов / прямых регистраций
        camp_users_q = select(func.count(AdvertisingCampaignRegistration.id)).where(
            AdvertisingCampaignRegistration.campaign_id == camp_id
        )
        camp_users_res = await db.execute(camp_users_q)
        direct_users = camp_users_res.scalar() or 0
        
        # Считаем общую выручку по кампании
        revenue_q = select(func.coalesce(func.sum(func.abs(Transaction.amount_kopeks)), 0)).join(
            AdvertisingCampaignRegistration,
            AdvertisingCampaignRegistration.user_id == Transaction.user_id
        ).where(
            AdvertisingCampaignRegistration.campaign_id == camp_id,
            Transaction.type.in_(['subscription_payment', 'deposit']),
            Transaction.is_completed.is_(True)
        )
        revenue_res = await db.execute(revenue_q)
        total_revenue = int(revenue_res.scalar() or 0)
        
        # Считаем платящих пользователей (конверсия)
        paid_users_q = select(func.count(func.distinct(Transaction.user_id))).join(
            AdvertisingCampaignRegistration,
            AdvertisingCampaignRegistration.user_id == Transaction.user_id
        ).where(
            AdvertisingCampaignRegistration.campaign_id == camp_id,
            Transaction.type.in_(['subscription_payment', 'deposit']),
            Transaction.is_completed.is_(True)
        )
        paid_users_res = await db.execute(paid_users_q)
        paid_users_count = paid_users_res.scalar() or 0
        
        conv_rate = round((paid_users_count / direct_users * 100), 2) if direct_users > 0 else 0.0
        avg_check = round(total_revenue / paid_users_count, 2) if paid_users_count > 0 else 0.0
        
        # Топ рефереры по этой кампании
        top_refs_q = select(
            User.id,
            User.username,
            func.count(User.id).label('invite_count')
        ).join(
            AdvertisingCampaignRegistration,
            AdvertisingCampaignRegistration.user_id == User.id
        ).where(
            AdvertisingCampaignRegistration.campaign_id == camp_id
        ).group_by(
            User.id
        ).order_by(
            desc('invite_count')
        ).limit(5)
        
        top_refs_res = await db.execute(top_refs_q)
        top_referrers = [
            {"user_id": row.id, "username": row.username, "referral_count": row.invite_count}
            for row in top_refs_res.all()
        ]
        
        nodes_campaigns_list.append(
            NetworkCampaignNode(
                id=camp.id,
                name=camp.name,
                start_parameter=camp.start_parameter,
                is_active=camp.is_active,
                direct_users=direct_users,
                total_network_users=direct_users,  # Упростим до количества прямых регистраций
                total_revenue_kopeks=total_revenue,
                conversion_rate=conv_rate,
                avg_check_kopeks=avg_check,
                top_referrers=top_referrers
            )
        )

    # 6. Статистические метаданные по всему графу
    edges_list = [NetworkEdge(source=s, target=t, type=ty) for s, t, ty in edges]
    
    # Общее количество уникальных пользователей на всем бэкенде для справки
    total_db_users = await db.execute(select(func.count(User.id)))
    total_db_referrers = await db.execute(select(func.count(func.distinct(User.referred_by_id))).where(User.referred_by_id.isnot(None)))
    total_db_campaigns = await db.execute(select(func.count(AdvertisingCampaign.id)))
    
    # Общая выручка от подписок
    total_revenue_db = await db.execute(
        select(func.coalesce(func.sum(func.abs(Transaction.amount_kopeks)), 0)).where(
            Transaction.type.in_(['subscription_payment', 'deposit']),
            Transaction.is_completed.is_(True)
        )
    )
    
    return NetworkGraphData(
        users=nodes_users_list,
        campaigns=nodes_campaigns_list,
        edges=edges_list,
        total_users=total_db_users.scalar() or len(nodes_users_list),
        total_referrers=total_db_referrers.scalar() or 0,
        total_campaigns=total_db_campaigns.scalar() or len(nodes_campaigns_list),
        total_earnings_kopeks=total_earnings_accumulated,
        total_subscription_revenue_kopeks=total_revenue_db.scalar() or 0
    )


@router.get('/user/{userId}', response_model=NetworkUserDetail)
async def get_user_detail(
    userId: int,
    admin: User = Depends(require_permission('partners:read')),
    db: AsyncSession = Depends(get_cabinet_db)
):
    """Детальная информация о пользователе для боковой панели."""
    logger.info("Загрузка деталей пользователя для графа реферальной сети", admin_id=admin.id, target_user_id=userId)
    
    user = await db.get(User, userId)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
        
    # Имя реферера (пригласителя)
    referrer_display_name = None
    if user.referred_by_id:
        referrer = await db.get(User, user.referred_by_id)
        if referrer:
            referrer_display_name = _get_display_name(referrer)
            
    # Кампания, через которую зарегистрировался
    campaign_name = None
    reg_q = select(AdvertisingCampaignRegistration).options(
        selectinload(AdvertisingCampaignRegistration.campaign)
    ).where(
        AdvertisingCampaignRegistration.user_id == userId
    )
    reg_res = await db.execute(reg_q)
    reg = reg_res.scalar_one_or_none()
    if reg and reg.campaign:
        campaign_name = reg.campaign.name
        
    # Активная подписка
    sub_q = select(Subscription).options(selectinload(Subscription.tariff)).where(
        Subscription.user_id == userId,
        Subscription.status == 'active'
    ).limit(1)
    sub_res = await db.execute(sub_q)
    sub = sub_res.scalar_one_or_none()
    
    sub_name = strip_telegram_tags(sub.tariff.name) if sub and sub.tariff else ("Пробный" if sub and sub.is_trial else None)
    sub_status = _determine_subscription_status(sub)
    sub_end_iso = sub.end_date.isoformat() if sub and sub.end_date else None
    
    # Расчет реферальных показателей
    direct_referrals_q = select(func.count(User.id)).where(User.referred_by_id == userId)
    direct_referrals_res = await db.execute(direct_referrals_q)
    direct_referrals_count = direct_referrals_res.scalar() or 0
    
    branch_users_count, branch_revenue = await _calculate_branch_stats(db, userId)
    personal_spent = await _get_personal_revenue(db, userId)
    
    return NetworkUserDetail(
        id=user.id,
        tg_id=user.telegram_id,
        username=user.username,
        email=user.email,
        display_name=_get_display_name(user),
        is_partner=user.partner_status == 'approved',
        referrer_id=user.referred_by_id,
        referrer_display_name=referrer_display_name,
        campaign_id=reg.campaign_id if reg else None,
        campaign_name=campaign_name,
        direct_referrals=direct_referrals_count,
        total_branch_users=branch_users_count,
        branch_revenue_kopeks=branch_revenue,
        personal_revenue_kopeks=personal_spent,
        personal_spent_kopeks=personal_spent,
        subscription_name=sub_name,
        subscription_end=sub_end_iso,
        subscription_status=sub_status,
        registered_at=user.created_at.isoformat() if user.created_at else None
    )


@router.get('/campaign/{campaignId}', response_model=NetworkCampaignDetail)
async def get_campaign_detail(
    campaignId: int,
    admin: User = Depends(require_permission('partners:read')),
    db: AsyncSession = Depends(get_cabinet_db)
):
    """Детальная информация о рекламной кампании для боковой панели."""
    logger.info("Загрузка деталей рекламной кампании для графа", admin_id=admin.id, campaign_id=campaignId)
    
    camp = await db.get(AdvertisingCampaign, campaignId)
    if not camp:
        raise HTTPException(status_code=404, detail="Кампания не найдена")
        
    # Считаем количество переходов / прямых регистраций
    camp_users_q = select(func.count(AdvertisingCampaignRegistration.id)).where(
        AdvertisingCampaignRegistration.campaign_id == campaignId
    )
    camp_users_res = await db.execute(camp_users_q)
    direct_users = camp_users_res.scalar() or 0
    
    # Считаем общую выручку по кампании
    revenue_q = select(func.coalesce(func.sum(func.abs(Transaction.amount_kopeks)), 0)).join(
        AdvertisingCampaignRegistration,
        AdvertisingCampaignRegistration.user_id == Transaction.user_id
    ).where(
        AdvertisingCampaignRegistration.campaign_id == campaignId,
        Transaction.type.in_(['subscription_payment', 'deposit']),
        Transaction.is_completed.is_(True)
    )
    revenue_res = await db.execute(revenue_q)
    total_revenue = int(revenue_res.scalar() or 0)
    
    # Считаем платящих пользователей (конверсия)
    paid_users_q = select(func.count(func.distinct(Transaction.user_id))).join(
        AdvertisingCampaignRegistration,
        AdvertisingCampaignRegistration.user_id == Transaction.user_id
    ).where(
        AdvertisingCampaignRegistration.campaign_id == campaignId,
        Transaction.type.in_(['subscription_payment', 'deposit']),
        Transaction.is_completed.is_(True)
    )
    paid_users_res = await db.execute(paid_users_q)
    paid_users_count = paid_users_res.scalar() or 0
    
    conv_rate = round((paid_users_count / direct_users * 100), 2) if direct_users > 0 else 0.0
    avg_check = round(total_revenue / paid_users_count, 2) if paid_users_count > 0 else 0.0
    
    # Топ рефереры по этой кампании
    top_refs_q = select(
        User.id,
        User.username,
        func.count(User.id).label('invite_count')
    ).join(
        AdvertisingCampaignRegistration,
        AdvertisingCampaignRegistration.user_id == User.id
    ).where(
        AdvertisingCampaignRegistration.campaign_id == campaignId
    ).group_by(
        User.id
    ).order_by(
        desc('invite_count')
    ).limit(5)
    
    top_refs_res = await db.execute(top_refs_q)
    top_referrers = [
        {"user_id": row.id, "username": row.username, "referral_count": row.invite_count}
        for row in top_refs_res.all()
    ]
    
    return NetworkCampaignDetail(
        id=camp.id,
        name=camp.name,
        start_parameter=camp.start_parameter,
        is_active=camp.is_active,
        direct_users=direct_users,
        total_network_users=direct_users,
        total_revenue_kopeks=total_revenue,
        conversion_rate=conv_rate,
        avg_check_kopeks=avg_check,
        top_referrers=top_referrers
    )


@router.get('/search', response_model=NetworkSearchResult)
async def search_network(
    q: str = Query(default="", min_length=1),
    admin: User = Depends(require_permission('partners:read')),
    db: AsyncSession = Depends(get_cabinet_db)
):
    """Живой поиск пользователей и рекламных кампаний по имени, юзернейму, email, TG_ID и параметру запуска."""
    logger.info("Поиск в реферальной сети", admin_id=admin.id, query=q)
    
    # 1. Поиск пользователей (до 15 результатов)
    users_conditions = []
    if q.isdigit():
        users_conditions.append(User.telegram_id == int(q))
    
    users_conditions.extend([
        User.username.ilike(f"%{q}%"),
        User.first_name.ilike(f"%{q}%"),
        User.last_name.ilike(f"%{q}%"),
        User.email.ilike(f"%{q}%")
    ])
    
    users_q = select(User).where(or_(*users_conditions)).limit(15)
    users_res = await db.execute(users_q)
    users = users_res.scalars().all()
    
    # Получаем регистрации и подписки для найденных пользователей
    user_ids = [u.id for u in users]
    user_registrations = {}
    user_subscriptions = {}
    referral_counts = {}
    
    if user_ids:
        # Регистрации
        regs_q = select(AdvertisingCampaignRegistration).where(AdvertisingCampaignRegistration.user_id.in_(user_ids))
        regs_res = await db.execute(regs_q)
        for r in regs_res.scalars().all():
            user_registrations[r.user_id] = r
            
        # Подписки
        subs_q = select(Subscription).options(selectinload(Subscription.tariff)).where(
            Subscription.user_id.in_(user_ids),
            Subscription.status == 'active'
        )
        subs_res = await db.execute(subs_q)
        for s in subs_res.scalars().all():
            user_subscriptions[s.user_id] = s
            
        # Прямые рефералы
        counts_q = select(User.referred_by_id, func.count(User.id)).where(
            User.referred_by_id.in_(user_ids)
        ).group_by(User.referred_by_id)
        counts_res = await db.execute(counts_q)
        for ref_id, count in counts_res.all():
            if ref_id is not None:
                referral_counts[ref_id] = count

    users_nodes_list = []
    for user in users:
        sub = user_subscriptions.get(user.id)
        sub_name = strip_telegram_tags(sub.tariff.name) if sub and sub.tariff else ("Пробный" if sub and sub.is_trial else None)
        sub_status = _determine_subscription_status(sub)
        sub_end_iso = sub.end_date.isoformat() if sub and sub.end_date else None
        
        branch_users_count, branch_revenue = await _calculate_branch_stats(db, user.id)
        personal_spent = await _get_personal_revenue(db, user.id)
        reg = user_registrations.get(user.id)
        
        users_nodes_list.append(
            NetworkUserNode(
                id=user.id,
                tg_id=user.telegram_id,
                username=user.username,
                email=user.email,
                display_name=_get_display_name(user),
                is_partner=user.partner_status == 'approved',
                referrer_id=user.referred_by_id,
                campaign_id=reg.campaign_id if reg else None,
                direct_referrals=referral_counts.get(user.id, 0),
                total_branch_users=branch_users_count,
                branch_revenue_kopeks=branch_revenue,
                personal_revenue_kopeks=personal_spent,
                personal_spent_kopeks=personal_spent,
                subscription_name=sub_name,
                subscription_end=sub_end_iso,
                subscription_status=sub_status,
                registered_at=user.created_at.isoformat() if user.created_at else None
            )
        )

    # 2. Поиск рекламных кампаний (до 15 результатов)
    campaigns_conditions = [
        AdvertisingCampaign.name.ilike(f"%{q}%"),
        AdvertisingCampaign.start_parameter.ilike(f"%{q}%")
    ]
    campaigns_q = select(AdvertisingCampaign).where(or_(*campaigns_conditions)).limit(15)
    campaigns_res = await db.execute(campaigns_q)
    campaigns = campaigns_res.scalars().all()
    
    campaigns_nodes_list = []
    for camp in campaigns:
        # Прямые регистрации
        camp_users_q = select(func.count(AdvertisingCampaignRegistration.id)).where(
            AdvertisingCampaignRegistration.campaign_id == camp.id
        )
        camp_users_res = await db.execute(camp_users_q)
        direct_users = camp_users_res.scalar() or 0
        
        # Общая выручка
        revenue_q = select(func.coalesce(func.sum(func.abs(Transaction.amount_kopeks)), 0)).join(
            AdvertisingCampaignRegistration,
            AdvertisingCampaignRegistration.user_id == Transaction.user_id
        ).where(
            AdvertisingCampaignRegistration.campaign_id == camp.id,
            Transaction.type.in_(['subscription_payment', 'deposit']),
            Transaction.is_completed.is_(True)
        )
        revenue_res = await db.execute(revenue_q)
        total_revenue = int(revenue_res.scalar() or 0)
        
        paid_users_q = select(func.count(func.distinct(Transaction.user_id))).join(
            AdvertisingCampaignRegistration,
            AdvertisingCampaignRegistration.user_id == Transaction.user_id
        ).where(
            AdvertisingCampaignRegistration.campaign_id == camp.id,
            Transaction.type.in_(['subscription_payment', 'deposit']),
            Transaction.is_completed.is_(True)
        )
        paid_users_res = await db.execute(paid_users_q)
        paid_users_count = paid_users_res.scalar() or 0
        
        conv_rate = round((paid_users_count / direct_users * 100), 2) if direct_users > 0 else 0.0
        avg_check = round(total_revenue / paid_users_count, 2) if paid_users_count > 0 else 0.0
        
        campaigns_nodes_list.append(
            NetworkCampaignNode(
                id=camp.id,
                name=camp.name,
                start_parameter=camp.start_parameter,
                is_active=camp.is_active,
                direct_users=direct_users,
                total_network_users=direct_users,
                total_revenue_kopeks=total_revenue,
                conversion_rate=conv_rate,
                avg_check_kopeks=avg_check,
                top_referrers=[]
            )
        )
        
    return NetworkSearchResult(users=users_nodes_list, campaigns=campaigns_nodes_list)
