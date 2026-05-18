from sqlalchemy import inspect
from app.database.models import Tariff

def main():
    print(f"=== Model: Tariff ===")
    mapper = inspect(Tariff)
    for attr in mapper.attrs:
        print(f"  - {attr.key}: {type(attr).__name__}")
    print()

if __name__ == "__main__":
    main()
