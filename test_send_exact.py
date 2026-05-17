import asyncio
from aiogram import Bot
from app.handlers.admin.messages import create_broadcast_keyboard

async def main():
    bot = Bot(token='8202792250:AAEWSnisLC37MKSegQad0KoPNevZz6Gzgcs')
    
    text = (
        '<tg-emoji emoji-id="5334675996714999970">🔹</tg-emoji> Мы обновили <b>сервис</b> – теперь доступ к звонкам, сообщениям, файлам и соцсетям без ограничений стал ещё удобнее!\xa0 \n\n'
        '<tg-emoji emoji-id="5357387758006448511">😊</tg-emoji> Воспользуйтесь промокодом <code>MOZHNOVSE</code> и получите дополнительную подписку <tg-emoji emoji-id="5323547156630483403">👍</tg-emoji>\n\n'
        '<tg-emoji emoji-id="5398001711786762757">✅</tg-emoji><b> Как активировать подарочный ПРОМОКОД</b>\xa0 \n'
        '<tg-emoji emoji-id="5305763715692377402">1️⃣</tg-emoji> Откройте бота и перейдите в <b>«Промокод»</b>.\xa0 \n'
        '<tg-emoji emoji-id="5307907239380528763">2️⃣</tg-emoji> Введите <code>MOZHNOVSE</code> – доступ к безлимиту будет активирован мгновенно.\xa0 \n'
        '<tg-emoji emoji-id="5305783000095537258">3️⃣</tg-emoji> Наслаждайтесь свободой в Telegram, YouTube и других сервисах.\n\n'
        '<tg-emoji emoji-id="5193018401810822951">🎉</tg-emoji><b> Новый функционал</b>\xa0 \n'
        '• Обновлённый сайт и личный кабинет – быстрый вход и простая настройка.\xa0 \n'
        '• Тестовая подписка в\xa0кабине доступна сразу после активации кода.\n'
        '• Привязка электронной почты для доступа к личному кабинету.\n'
        '• Ссылка на сайт работает постоянно, если даже у вас нет доступа в телеграм. \n\n'
        '<tg-emoji emoji-id="5436113877181941026">❓</tg-emoji><b> Не можете открыть Telegram?</b>\xa0 \n'
        'Перейдите в личный кабинет на сайте, активируйте тестовую подписку и получайте доступ к Telegram и другим соцсетям без проблем.\xa0 \n\n'
        '<b>🤝 Поделитесь с другом</b> – используйте кнопку <b>«Поделиться с другом»</b> в боте, чтобы отправить им свою реферальную ссылку.\xa0 \n\n'
        '<tg-emoji emoji-id="5215399343246289016">™️</tg-emoji> <b>Вперёд к свободному интернету!</b>'
    )
    
    selected_buttons = ['home', 'promocode', 'referrals']
    keyboard = create_broadcast_keyboard(selected_buttons, 'ru')
    video_id = 'BAACAgIAAxkBAAIhyWoKGNSCo4vtC5wpHl90lR4DJwveAAJWnQACAfCoShu7iAnRlixJOwQ'
    
    try:
        await bot.send_video(
            chat_id=6521050178,
            video=video_id,
            caption=text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
        print('SUCCESS: Message sent!')
    except Exception as e:
        print('ERROR:', type(e).__name__, str(e))
    finally:
        await bot.session.close()

asyncio.run(main())
