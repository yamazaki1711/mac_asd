import logging
from src.db.init_db import Session
from src.db.models import Vendor, MaterialCatalog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SEED_LOGISTICS")

def seed_data():
    """Наполнение базы начальными данными для логистики."""
    logger.info("Seeding initial logistics data...")
    
    with Session() as session:
        # 1. Поставщики
        vendors = [
            Vendor(
                name="ООО 'МеталлИнвест'", 
                category="Materials", 
                inn="7701234567", 
                contact_info={"email": "sales@metalinvest.ru", "phone": "+7 495 123-4567"}
            ),
            Vendor(
                name="ПАО 'Северсталь'", 
                category="Materials", 
                inn="3528000597", 
                contact_info={"email": "info@severstal.com", "phone": "+7 8202 53-0900"}
            ),
            Vendor(
                name="ООО 'ТехноНиколь'", 
                category="Materials", 
                inn="7702521529", 
                contact_info={"email": "supply@tn.ru", "phone": "+7 495 925-1055"}
            )
        ]
        
        # 2. Материалы
        materials = [
            MaterialCatalog(name="Шпунт Ларсена Л5-УМ", category="Металл", unit="т", avg_price=12000000), # 120 000 руб/т
            MaterialCatalog(name="Арматура А500С 12мм", category="Металл", unit="т", avg_price=6500000),  # 65 000 руб/т
            MaterialCatalog(name="Бетон В25 (М350)", category="Бетон", unit="м3", avg_price=650000),      # 6 500 руб/м3
            MaterialCatalog(name="Шебень гранитный 20-40", category="Инертные", unit="м3", avg_price=250000) # 2 500 руб/м3
        ]

        try:
            # Добавляем только если еще нет таких записей (упрощенно)
            for v in vendors:
                exists = session.query(Vendor).filter_by(inn=v.inn).first()
                if not exists:
                    session.add(v)
            
            for m in materials:
                exists = session.query(MaterialCatalog).filter_by(name=m.name).first()
                if not exists:
                    session.add(m)
            
            session.commit()
            logger.info("Logistics data seeded successfully.")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to seed data: {e}")

if __name__ == "__main__":
    seed_data()
