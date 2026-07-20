import asyncio
import sys
sys.path.insert(0, '.')
from database import set_db_path, init_db, export_data
import config

async def main():
    set_db_path(config.DATABASE_PATH)
    await init_db()
    file = await export_data()
    print(f"Данные сохранены в {file}")

asyncio.run(main())