import json
import base64
import time
from urllib.parse import urlparse
import structlog
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from app.config import settings

# Настраиваем структурированное логирование для отладки и мониторинга
logger = structlog.get_logger(__name__)

def urlsafe_b64encode_no_padding(data: bytes) -> str:
    """Кодирует байты в URL-safe Base64 без заполняющих символов '='."""
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

def generate_vapid_headers(endpoint: str) -> dict[str, str]:
    """
    Генерирует заголовки авторизации VAPID для отправки Web Push уведомлений.
    Реализует спецификацию RFC 8292.
    Избегает использования проблемной библиотеки py-vapid,
    напрямую подписывая JWT с помощью библиотеки cryptography.
    
    :param endpoint: URL-адрес push-службы получателя (например, fcm.googleapis.com)
    :return: Словарь с HTTP-заголовками, например {"Authorization": "vapid t=..., k=..."}
    """
    try:
        # Проверяем наличие ключей в настройках
        if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
            logger.error("VAPID ключи не настроены или отсутствуют на сервере")
            return {}
            
        logger.info("Начало генерации VAPID заголовка", endpoint=endpoint[:40])
        
        # 1. Извлекаем приватный ключ из настроек (Base64url строка)
        # Добавляем необходимое дополнение '===' для успешного декодирования
        priv_bytes = base64.urlsafe_b64decode(settings.VAPID_PRIVATE_KEY + "===")
        
        # Превращаем байты приватного ключа в целое число
        priv_num = int.from_bytes(priv_bytes, byteorder='big')
        
        # Получаем объект приватного ключа на эллиптической кривой NIST P-256 (SECP256R1)
        # Обратите внимание: мы вызываем ec.SECP256R1() с круглыми скобками, что создает инстанс кривой.
        # Это предотвращает ошибку "Curve must be an instance of EllipticCurve" на новых версиях cryptography.
        private_key = ec.derive_private_key(priv_num, ec.SECP256R1())
        
        # 2. Формируем заголовок JWT (typ и alg)
        jwt_header = {"typ": "JWT", "alg": "ES256"}
        
        # 3. Выделяем аудиторию (aud) из endpoint (схема + хост)
        url = urlparse(endpoint)
        aud = f"{url.scheme}://{url.netloc}"
        
        # 4. Формируем тело JWT (claims)
        # Время жизни токена — 12 часов (согласно стандарту Web Push)
        payload = {
            "aud": aud,
            "exp": int(time.time()) + 12 * 3600,
            "sub": settings.VAPID_CLAIM_EMAIL
        }
        
        # 5. Кодируем заголовок и тело в URL-safe Base64 без паддинга
        header_b64 = urlsafe_b64encode_no_padding(json.dumps(jwt_header).encode('utf-8'))
        payload_b64 = urlsafe_b64encode_no_padding(json.dumps(payload).encode('utf-8'))
        
        # Подготавливаем строку для подписи
        signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
        
        # 6. Подписываем входные данные с помощью ECDSA (с хэшированием SHA256)
        raw_sig = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        
        # 7. Преобразуем DER-подпись (которую возвращает cryptography) в формат IEEE P1363 (r || s, 64 байта)
        r, s = decode_dss_signature(raw_sig)
        r_bytes = r.to_bytes(32, byteorder='big')
        s_bytes = s.to_bytes(32, byteorder='big')
        
        # Кодируем подпись в URL-safe Base64
        sig_b64 = urlsafe_b64encode_no_padding(r_bytes + s_bytes)
        
        # 8. Собираем JWT-токен целиком
        jwt_token = f"{header_b64}.{payload_b64}.{sig_b64}"
        
        # 9. Формируем заголовок Authorization
        vapid_auth_header = f"vapid t={jwt_token}, k={settings.VAPID_PUBLIC_KEY}"
        
        logger.info("VAPID заголовок успешно сгенерирован")
        return {"Authorization": vapid_auth_header}
        
    except Exception as e:
        logger.error("Ошибка при генерации VAPID заголовка", error=str(e))
        return {}
