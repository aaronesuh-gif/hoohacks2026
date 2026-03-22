"""
cluster_database.py
-------------------
SQLite + SQLAlchemy database for storing 7 clusters with like/dislike counts.
"""

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# ---------------------------------------------------------------------------
# Base & Engine
# ---------------------------------------------------------------------------

DATABASE_URL = "sqlite:///Database/clusters.db"
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class Cluster(Base):
    """One cluster with an like and dislike count."""

    __tablename__ = "clusters"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    name      = Column(String, nullable=False, unique=True)  # e.g. "Cluster 1"
    likes   = Column(Integer, default=0, nullable=False)
    dislikes = Column(Integer, default=0, nullable=False)
    ingredients = Column(String, nullable=True)

    def __repr__(self):
        return f"<Cluster name={self.name!r} likes={self.likes} dislikes={self.dislikes}>"


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------

class ClusterDatabase:

    NUM_CLUSTERS = 7

    def __init__(self):
        Base.metadata.create_all(engine)
        self._Session = SessionLocal
        self._seed_clusters()

    def _seed_clusters(self):
        """Create the 7 clusters if they don't exist yet."""
        with self._Session() as session:
            existing = session.query(Cluster).count()
            if existing == 0:
                clusters = [
                    Cluster(name=f"Cluster {i}", likes=0, dislikes=0)
                    for i in range(1, self.NUM_CLUSTERS + 1)
                ]
                session.add_all(clusters)
                session.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_all_clusters(self) -> list[Cluster]:
        """Return all 7 clusters."""
        with self._Session() as session:
            return session.query(Cluster).order_by(Cluster.id).all()

    def get_cluster(self, name: str) -> Cluster | None:
        """Return a single cluster by name, or None if not found."""
        with self._Session() as session:
            return session.query(Cluster).filter(Cluster.name == name).first()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def like(self, cluster_name: str) -> bool:
        """Increment the like count for a cluster. Returns True on success."""
        with self._Session() as session:
            cluster = session.query(Cluster).filter(Cluster.name == cluster_name).first()
            if cluster is None:
                return False
            cluster.likes += 1
            session.commit()
            return True

    def dislike(self, cluster_name: str) -> bool:
        """Increment the dislike count for a cluster. Returns True on success."""
        with self._Session() as session:
            cluster = session.query(Cluster).filter(Cluster.name == cluster_name).first()
            if cluster is None:
                return False
            cluster.dislikes += 1
            session.commit()
            return True

    def reset_votes(self, cluster_name: str) -> bool:
        """Reset likes and dislikes to 0 for a cluster."""
        with self._Session() as session:
            cluster = session.query(Cluster).filter(Cluster.name == cluster_name).first()
            if cluster is None:
                return False
            cluster.likes = 0
            cluster.dislikes = 0
            session.commit()
            return True

    def reset_all(self):
        """Reset votes on all 7 clusters."""
        with self._Session() as session:
            session.query(Cluster).update({"likes": 0, "dislikes": 0})
            session.commit()


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
 
if __name__ == "__main__":
    db = ClusterDatabase()
 
    db.like("Cluster 1")
    db.like("Cluster 1")
    db.dislike("Cluster 1")
    db.like("Cluster 3")
 
    for cluster in db.get_all_clusters():
        print(cluster)