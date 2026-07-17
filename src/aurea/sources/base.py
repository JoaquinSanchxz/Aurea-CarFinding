from typing import Protocol, List, Optional, Dict, Any
from pydantic import BaseModel, Field
from aurea.config import SearchConfig

class RawListing(BaseModel):
    source_id: str
    source: str  # wallapop, milanuncios, coches_net
    title: str
    description: str
    url: str
    price: float
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    mileage_km: Optional[int] = None
    fuel: Optional[str] = None
    transmission: Optional[str] = None
    location: Optional[str] = None
    published_at: Optional[str] = None  # Raw date representation
    raw_data: Dict[str, Any] = Field(default_factory=dict)

class SourceConnector(Protocol):
    name: str

    def collect(self, search: SearchConfig) -> List[RawListing]:
        ...
