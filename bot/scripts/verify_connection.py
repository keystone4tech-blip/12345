import asyncio
import sys
import os

# Добавляем путь к корню проекта
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.external.remnawave_api import RemnaWaveAPI, RemnaWaveAPIError
from app.config import settings

async def main():
    # Данные из вашего запроса
    url = "https://p.mozhnovpn.tech"
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1dWlkIjoiNTc2NjY3ZjgtNTY2YS00NDlkLWIwN2EtMmViZDgwODA5YjA1IiwidXNlcm5hbWUiOm51bGwsInJvbGUiOiJBUEkiLCJpYXQiOjE3NzYyODM0MzUsImV4cCI6MTA0MTYxOTcwMzV9.1NZ-kzsMLsTgiUHW44K4TJBtyWxTHQzQAUWrL2EPrYg"
    
    print(f"--- Тестирование подключения к {url} ---")
    
    api = RemnaWaveAPI(
        base_url=url,
        api_key=token,
        auth_type='bearer'
    )
    
    try:
        async with api:
            print("[1/2] Проверка связи (System Stats)...")
            stats = await api.get_system_stats()
            print(f"Успех! Статус системы получен.")
            # print(f"Данные: {stats}")
            
            print("[2/2] Проверка списка нод...")
            nodes = await api.get_all_nodes()
            print(f"Успех! Найдено нод: {len(nodes)}")
            for node in nodes:
                print(f" - Нода: {node.name} ({node.address}) | Статус: {'Online' if node.is_connected else 'Offline'}")
            
            print("\nВсё работает корректно!")
            
    except RemnaWaveAPIError as e:
        print(f"\nОшибка API ({e.status_code}): {e.message}")
        if e.response_data:
            print(f"Детали: {e.response_data}")
    except Exception as e:
        print(f"\nНепредвиденная ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
