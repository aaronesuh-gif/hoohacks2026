"""
database.py
-----------
SQLite + SQLAlchemy database for storing dining hall menu items.
The database file (dining.db) is created automatically on first run.
"""

from datetime import datetime
from typing import Optional
 
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ---------------------------------------------------------------------------
# Base & Engine
# ---------------------------------------------------------------------------
 
DATABASE_URL = "sqlite:///dining.db"
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
    dining_hall = Column(String, nullable=False)          # e.g. "Newcomb", "Runk"
    category    = Column(String, nullable=True)           # e.g. "Entrées", "Salad Bar"
 
    # --- Nutrition (all per-serving, nullable in case scraper can't find them) ---
    serving_size = Column(String,  nullable=True)         # e.g. "1 cup", "4 oz"
    calories = Column(Integer, nullable=True)
    total_fat_g = Column(Float,   nullable=True)
    saturated_fat_g = Column(Float, nullable=True)
    trans_fat_g = Column(Float,   nullable=True)
    cholesterol_mg = Column(Float, nullable=True)
    sodium_mg = Column(Float,   nullable=True)
    total_carbs_g = Column(Float, nullable=True)
    dietary_fiber_g = Column(Float, nullable=True)
    total_sugars_g = Column(Float, nullable=True)
    protein_g = Column(Float,   nullable=True)
 
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

    #
 
    def __repr__(self) -> str:
        return f"<DiningItem id={self.id} name={self.name!r} hall={self.dining_hall!r}>"
    
# ---------------------------------------------------------------------------
# Database helper class
# ---------------------------------------------------------------------------
 
class Database:
    """Thin wrapper around the SQLAlchemy session for common operations."""
 
    def __init__(self):
        # Create all tables if they don't exist yet
        Base.metadata.create_all(engine)
        self._Session = SessionLocal
 
    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
 
    def add_item(self, item_data: dict) -> DiningItem:
        """
        Insert a single dining item.
 
        Parameters
        ----------
        item_data : dict
            Keys should match DiningItem column names.
 
        Returns
        -------
        DiningItem
            The newly created (and committed) ORM object.
 
        Example
        -------
        db.add_item({
            "name": "Grilled Chicken",
            "dining_hall": "Newcomb",
            "calories": 280,
            "protein_g": 34,
            "is_gluten_free": True,
        })
        """
        with self._Session() as session:
            item = DiningItem(**item_data)
            session.add(item)
            session.commit()
            session.refresh(item)
            return item
        
    def add_items(self, items: list[dict]) -> int:
        """
        Bulk-insert a list of item dicts. Much faster than calling
        add_item() in a loop for large scraper payloads.
 
        Returns the number of rows inserted.
        """
        with self._Session() as session:
            session.bulk_insert_mappings(DiningItem, items)
            session.commit()
            return len(items)
    
    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
 
    def get_all_items(self) -> list[DiningItem]:
        """Return every item in the database."""
        with self._Session() as session:
            return session.query(DiningItem).all()
 
    def get_items_by_hall(self, dining_hall: str) -> list[DiningItem]:
        """Return all items for a specific dining hall (case-insensitive)."""
        with self._Session() as session:
            return (
                session.query(DiningItem)
                .filter(DiningItem.dining_hall.ilike(dining_hall))
                .all()
            )
 
    def get_item_by_id(self, item_id: int) -> Optional[DiningItem]:
        """Return a single item by primary key, or None if not found."""
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
        """
        Return items that match ALL of the requested dietary tags.
 
        Example
        -------
        vegan_gf_items = db.filter_by_tags(vegan=True, gluten_free=True)
        """
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
        """Fuzzy name search (SQL LIKE, case-insensitive)."""
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
        """Delete every row. Returns the number of rows deleted."""
        with self._Session() as session:
            count = session.query(DiningItem).delete()
            session.commit()
            return count
 
    def delete_item(self, item_id: int) -> bool:
        """Delete one item by id. Returns True if it existed."""
        with self._Session() as session:
            item = session.get(DiningItem, item_id)
            if item is None:
                return False
            session.delete(item)
            session.commit()
            return True
        

# ---------------------------------------------------------------------------
# Quick smoke-test (run this file directly to verify setup)
# ---------------------------------------------------------------------------
 
if __name__ == "__main__":
    db = Database()
 
    db.add_item({
        "name": "Grilled Chicken Breast",
        "dining_hall": "Newcomb",
        "category": "Entrées",
        "calories": 280,
        "protein_g": 34,
        "total_fat_g": 6,
        "sodium_mg": 410,
        "is_gluten_free": True,
        "is_halal": True,
    })
 
    db.add_item({
        "name": "Black Bean Burger",
        "dining_hall": "Runk",
        "category": "Grill",
        "calories": 390,
        "protein_g": 16,
        "total_carbs_g": 52,
        "is_vegan": True,
        "is_vegetarian": True,
    })
 
    items = db.get_all_items()
    print(f"Total items in DB: {len(items)}")
    for item in items:
        print(f"  {item.name} @ {item.dining_hall} — {item.calories} cal")
 
    vegan = db.filter_by_tags(vegan=True)
    print(f"\nVegan items: {[i.name for i in vegan]}")
 