from datetime import datetime
from typing import List, Optional
from sqlmodel import Field, SQLModel, Relationship

class Listing(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: str = Field(index=True)
    source: str = Field(index=True) # wallapop, milanuncios, coches_net
    title: str
    description: str
    url: str
    price: float
    make: str
    model: str
    generation: Optional[str] = None
    engine: Optional[str] = None
    year: int
    mileage_km: int
    fuel: str
    transmission: str
    location: Optional[str] = None
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)
    raw_data: Optional[str] = None # JSON string
    is_aurea: bool = Field(default=False)
    rating: float = Field(default=0.0)
    opportunity_id: Optional[str] = Field(default=None, unique=True, index=True)

    # Relationships
    price_history: List["PriceHistory"] = Relationship(back_populates="listing", cascade_delete=True)
    evaluations: List["Evaluation"] = Relationship(back_populates="listing", cascade_delete=True)
    notifications: List["Notification"] = Relationship(back_populates="listing", cascade_delete=True)

class PriceHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    listing_id: int = Field(foreign_key="listing.id", index=True)
    price: float
    detected_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    listing: Listing = Relationship(back_populates="price_history")

class Evaluation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    listing_id: int = Field(foreign_key="listing.id", index=True)
    score_global: float
    risk_score: float
    market_confidence: float
    vehicle_confidence: float
    num_comparables: int
    discount_percent: float
    saving_eur: float
    adjusted_saving_eur: float
    reliability_score: float
    parts_availability_score: float
    parts_cost_score: float
    maintenance_score: float
    efficiency_score: float
    performance_balance_score: float
    resale_score: float
    coherency_score: float
    reasons: str # Comma-separated or JSON
    warnings: str # Comma-separated or JSON
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    listing: Listing = Relationship(back_populates="evaluations")
    comparables: List["ComparableVehicle"] = Relationship(back_populates="evaluation", cascade_delete=True)

class ComparableVehicle(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    evaluation_id: int = Field(foreign_key="evaluation.id", index=True)
    title: str
    price: float
    mileage_km: int
    year: int
    url: Optional[str] = None

    # Relationships
    evaluation: Evaluation = Relationship(back_populates="comparables")

class Notification(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    listing_id: int = Field(foreign_key="listing.id", index=True)
    opportunity_id: str = Field(index=True)
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    status: str # "sent", "failed"
    error_message: Optional[str] = None

    # Relationships
    listing: Listing = Relationship(back_populates="notifications")

class ExecutionError(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    source: Optional[str] = None
    error_message: str
    occurred_at: datetime = Field(default_factory=datetime.utcnow)

class LocationCoordinate(SQLModel, table=True):
    name: str = Field(primary_key=True)
    latitude: float
    longitude: float

