"""
database.py
-----------
SQLite + SQLAlchemy database for storing dining hall menu items.
The database file (dining.db) is created automatically on first run.
"""

from typing import Optional
 
from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ---------------------------------------------------------------------------
# Base & Engine
# ---------------------------------------------------------------------------
 
DATABASE_URL = "sqlite:///Database/dining.db"
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
 
 
class Base(DeclarativeBase):
    pass

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
 
class DiningItem(Base):
    """One menu item scraped from a dining hall."""
 
    __tablename__ = "dining_items"
 
    id = Column(Integer, primary_key=True, autoincrement=True)
 
    # --- Identity ---
    name        = Column(String, nullable=False)
    dining_hall = Column(String, nullable=False)
    category    = Column(String, nullable=True)
    meal_period = Column(String, nullable=True)           # Breakfast, Lunch, Dinner, Brunch

    # --- Item type ---
    # "main"   = standalone meal
    # "topping" = low cal topping (<50 cal), shown as optional add-on
    # "combo"  = auto-generated base meal + high-cal topping (>=50 cal)
    item_type         = Column(String,  nullable=True, default="main")
    base_meal_name    = Column(String,  nullable=True)    # for combos: name of the base meal
    topping_name      = Column(String,  nullable=True)    # for combos: name of the high-cal topping added
    has_low_cal_toppings = Column(Boolean, default=False) # True if <50 cal toppings are available for this meal

    # --- Nutrition (all per-serving, nullable in case scraper can't find them) ---
    serving_size    = Column(String,  nullable=True)
    calories        = Column(Integer, nullable=True)
    total_fat_g     = Column(Float,   nullable=True)
    saturated_fat_g = Column(Float,   nullable=True)
    trans_fat_g     = Column(Float,   nullable=True)
    cholesterol_mg  = Column(Float,   nullable=True)
    sodium_mg       = Column(Float,   nullable=True)
    total_carbs_g   = Column(Float,   nullable=True)
    dietary_fiber_g = Column(Float,   nullable=True)
    total_sugars_g  = Column(Float,   nullable=True)
    protein_g       = Column(Float,   nullable=True)
 
    # --- Dietary tags (True = item meets that label) ---
    is_vegan          = Column(Boolean, default=False)
    is_vegetarian     = Column(Boolean, default=False)
    is_gluten_free    = Column(Boolean, default=False)
    is_halal          = Column(Boolean, default=False)
    is_kosher         = Column(Boolean, default=False)
    contains_nuts     = Column(Boolean, default=False)
    contains_dairy    = Column(Boolean, default=False)
    contains_eggs     = Column(Boolean, default=False)
    contains_soy      = Column(Boolean, default=False)
    contains_shellfish = Column(Boolean, default=False)
 
    def __repr__(self) -> str:
        return f"<DiningItem id={self.id} name={self.name!r} hall={self.dining_hall!r}>"
    
# ---------------------------------------------------------------------------
# Database helper class
# ---------------------------------------------------------------------------
 
class Database:
    """Thin wrapper around the SQLAlchemy session for common operations."""
 
    def __init__(self):
        Base.metadata.create_all(engine)
        self._Session = SessionLocal
 
    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
 
    def add_item(self, item_data: dict) -> DiningItem:
        with self._Session() as session:
            item = DiningItem(**item_data)
            session.add(item)
            session.commit()
            session.refresh(item)
            return item
        
    def add_items(self, items: list[dict]) -> int:
        with self._Session() as session:
            session.bulk_insert_mappings(DiningItem, items)
            session.commit()
            return len(items)
    
    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
 
    def get_all_items(self) -> list[DiningItem]:
        with self._Session() as session:
            return session.query(DiningItem).all()
 
    def get_items_by_hall(self, dining_hall: str) -> list[DiningItem]:
        with self._Session() as session:
            return (
                session.query(DiningItem)
                .filter(DiningItem.dining_hall.ilike(dining_hall))
                .all()
            )

    def get_items_by_meal_period(self, meal_period: str) -> list[DiningItem]:
        """Return all items for a specific meal period (case-insensitive)."""
        with self._Session() as session:
            return (
                session.query(DiningItem)
                .filter(DiningItem.meal_period.ilike(meal_period))
                .all()
            )

    def get_main_meals(self) -> list[DiningItem]:
        """Return only standalone main meals (not toppings or combos)."""
        with self._Session() as session:
            return (
                session.query(DiningItem)
                .filter(DiningItem.item_type == "main")
                .all()
            )

    def get_combos(self) -> list[DiningItem]:
        """Return all auto-generated combo meals."""
        with self._Session() as session:
            return (
                session.query(DiningItem)
                .filter(DiningItem.item_type == "combo")
                .all()
            )

    def get_toppings(self) -> list[DiningItem]:
        """Return all low-cal toppings (<50 cal)."""
        with self._Session() as session:
            return (
                session.query(DiningItem)
                .filter(DiningItem.item_type == "topping")
                .all()
            )
 
    def get_item_by_id(self, item_id: int) -> Optional[DiningItem]:
        with self._Session() as session:
            return session.get(DiningItem, item_id)
 
    def filter_by_tags(
        self,
        vegan: bool = False,
        vegetarian: bool = False,
        gluten_free: bool = False,
        halal: bool = False,
        kosher: bool = False,
    ) -> list[DiningItem]:
        with self._Session() as session:
            query = session.query(DiningItem)
            if vegan:
                query = query.filter(DiningItem.is_vegan == True)
            if vegetarian:
                query = query.filter(DiningItem.is_vegetarian == True)
            if gluten_free:
                query = query.filter(DiningItem.is_gluten_free == True)
            if halal:
                query = query.filter(DiningItem.is_halal == True)
            if kosher:
                query = query.filter(DiningItem.is_kosher == True)
            return query.all()
 
    def search_by_name(self, query: str) -> list[DiningItem]:
        with self._Session() as session:
            return (
                session.query(DiningItem)
                .filter(DiningItem.name.ilike(f"%{query}%"))
                .all()
            )
    
    # ------------------------------------------------------------------
    # Delete / maintenance
    # ------------------------------------------------------------------
 
    def clear_all(self) -> int:
        with self._Session() as session:
            count = session.query(DiningItem).delete()
            session.commit()
            return count
 
    def delete_item(self, item_id: int) -> bool:
        with self._Session() as session:
            item = session.get(DiningItem, item_id)
            if item is None:
                return False
            session.delete(item)
            session.commit()
            return True