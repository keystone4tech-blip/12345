import sys, re

path = 'bot/app/handlers/start.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target = '''    info_sections: list[str] = []

    try:
        promo_hint = await build_promo_offer_hint(db, user, texts)'''

replacement = '''    info_sections: list[str] = []

    try:
        if settings.REVIEWS_ENABLED or getattr(settings, 'REVIEWS_BUTTON_ENABLED', False):
            from app.services.reviews_service import reviews_service
            stats = await reviews_service.get_review_stats(db)
            if stats['total'] > 0 and stats['avg_rating'] > 0:
                review_hint = texts.t(
                    'MAIN_MENU_REVIEWS_RATING',
                    '⭐ <b>Оценка нашего сервиса: {avg_rating}</b>, основанная на отзывах пользователей. Посмотреть отзывы можно по кнопке ниже.'
                ).format(avg_rating=stats['avg_rating'])
                info_sections.append(review_hint)
    except Exception as e:
        logger.error('Ошибка получения статистики отзывов для главного меню', error=e)

    try:
        promo_hint = await build_promo_offer_hint(db, user, texts)'''

if target in content:
    content = content.replace(target, replacement)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully updated start.py")
else:
    print("Could not find target in start.py")
