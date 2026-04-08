import structlog
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from app.database.database import engine
from app.database.models import Base

logger = structlog.get_logger(__name__)

def _get_column_sql_type(column, dialect):
    """Попытка получить SQL-представление типа колонки."""
    try:
        return column.type.compile(dialect=dialect)
    except Exception:
        # Фолбек для сложных типов
        type_name = str(column.type).upper()
        if 'JSON' in type_name:
            return 'JSONB'
        if 'VARCHAR' in type_name:
            return 'VARCHAR'
        if 'BOOLEAN' in type_name:
            return 'BOOLEAN'
        if 'INTEGER' in type_name:
            return 'INTEGER'
        if 'BIGINT' in type_name:
            return 'BIGINT'
        if 'TIMESTAMP' in type_name:
            return 'TIMESTAMP'
        return type_name

def sync_schema_blocking(conn: Connection):
    """Синхронизация схемы в синхронном контексте (используется через run_sync)."""
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    dialect = conn.dialect

    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            logger.info("Таблица не найдена, пропускаем (должна создаться через create_all)", table=table_name)
            continue

        # Получаем структуру существующей таблицы
        db_columns = {col['name']: col for col in inspector.get_columns(table_name)}
        
        for column in table.columns:
            if column.name not in db_columns:
                logger.warning("Обнаружена отсутствующая колонка, добавляю...", table=table_name, column=column.name)
                
                type_sql = _get_column_sql_type(column, dialect)
                nullable = "NULL" if column.nullable else "NOT NULL"
                default_clause = ""
                
                # Добавление колонки через ALTER TABLE
                # Мы используем простые команды, чтобы минимизировать риск ошибок
                sql = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{column.name}" {type_sql} {nullable}'
                
                try:
                    conn.execute(text(sql))
                    logger.info("Колонка успешно добавлена", table=table_name, column=column.name)
                except Exception as e:
                    logger.error("Ошибка при добавлении колонки", table=table_name, column=column.name, error=str(e))

async def sync_database_schema():
    """Асинхронный запуск синхронизации схемы БД."""
    logger.info("Запуск автоматической синхронизации схемы БД...")
    
    try:
        async with engine.begin() as conn:
            # Создаем все недостающие таблицы (безопасно)
            await conn.run_sync(Base.metadata.create_all)
            
            # Проверяем недостающие колонки
            await conn.run_sync(sync_schema_blocking)
            
        logger.info("Синхронизация схемы БД завершена успешно")
        return True
    except Exception as e:
        logger.error("Критическая ошибка при синхронизации схемы БД", error=str(e))
        return False
