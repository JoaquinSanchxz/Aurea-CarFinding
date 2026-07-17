import logging
from typing import List
from datetime import datetime, timedelta
import httpx
from aurea.config import SearchConfig, load_settings
from aurea.sources.base import SourceConnector, RawListing

logger = logging.getLogger("aurea.sources.coches_net")

class CochesNetConnector(SourceConnector):
    name = "coches_net"

    def collect(self, search: SearchConfig) -> List[RawListing]:
        settings = load_settings()
        results: List[RawListing] = []
        
        if not settings.scraping.use_fixtures_fallback:
            try:
                # Mock live request structure
                pass
            except Exception as e:
                logger.warning(f"Coches.net request failed: {e}. Falling back to fixtures.")

        fixtures = get_coches_net_fixtures()
        
        for f in fixtures:
            if search.price.max_price_eur and f.price > search.price.max_price_eur:
                continue
            if search.vehicle.min_year and f.year < search.vehicle.min_year:
                continue
            if search.vehicle.max_mileage_km and f.mileage_km > search.vehicle.max_mileage_km:
                continue
            if search.vehicle.fuels and f.fuel not in search.vehicle.fuels:
                continue
            if search.vehicle.makes and f.make not in search.vehicle.makes:
                continue
            results.append(f)
            
        return results

def get_coches_net_fixtures() -> List[RawListing]:
    now = datetime.utcnow()
    # Return multiple Corollas to act as high-quality comparables
    return [
        RawListing(
            source_id="cn_001",
            source="coches_net",
            title="Toyota Corolla 1.8 125H Active Tech",
            description="Coche impecable, un solo propietario. Garantia oficial Toyota.",
            url="https://www.coches.net/toyota-corolla-cn_001.aspx",
            price=22900.0,
            make="Toyota",
            model="Corolla",
            year=2021,
            mileage_km=75000,
            fuel="hybrid",
            transmission="automatic",
            location="Madrid, ES",
            published_at=(now - timedelta(days=1)).isoformat(),
            raw_data={"source": "coches_net", "id": "cn_001"}
        ),
        RawListing(
            source_id="cn_002",
            source="coches_net",
            title="Toyota Corolla Hybrid Style",
            description="Toyota Corolla de ocasion, garantia oficial.",
            url="https://www.coches.net/toyota-corolla-cn_002.aspx",
            price=23500.0,
            make="Toyota",
            model="Corolla",
            year=2021,
            mileage_km=65000,
            fuel="hybrid",
            transmission="automatic",
            location="Valencia, ES",
            published_at=(now - timedelta(days=2)).isoformat(),
            raw_data={"source": "coches_net", "id": "cn_002"}
        ),
        RawListing(
            source_id="cn_003",
            source="coches_net",
            title="Toyota Corolla Hatchback Active Tech",
            description="Particular vende por no usar. Muy cuidado, garaje.",
            url="https://www.coches.net/toyota-corolla-cn_003.aspx",
            price=21900.0,
            make="Toyota",
            model="Corolla",
            year=2021,
            mileage_km=80000,
            fuel="hybrid",
            transmission="automatic",
            location="Sevilla, ES",
            published_at=(now - timedelta(days=3)).isoformat(),
            raw_data={"source": "coches_net", "id": "cn_003"}
        ),
        RawListing(
            source_id="cn_004",
            source="coches_net",
            title="Toyota Corolla 122h Active Tech",
            description="Vehículo en excelentes condiciones, revisado.",
            url="https://www.coches.net/toyota-corolla-cn_004.aspx",
            price=24000.0,
            make="Toyota",
            model="Corolla",
            year=2021,
            mileage_km=55000,
            fuel="hybrid",
            transmission="automatic",
            location="Zaragoza, ES",
            published_at=(now - timedelta(days=4)).isoformat(),
            raw_data={"source": "coches_net", "id": "cn_004"}
        ),
        RawListing(
            source_id="cn_005",
            source="coches_net",
            title="Toyota Corolla 1.8 Hybrid 122 Active Tech 5d",
            description="Impecable estado. Revisiones oficiales al dia.",
            url="https://www.coches.net/toyota-corolla-cn_005.aspx",
            price=22800.0,
            make="Toyota",
            model="Corolla",
            year=2021,
            mileage_km=71000,
            fuel="hybrid",
            transmission="automatic",
            location="Malaga, ES",
            published_at=(now - timedelta(days=2)).isoformat(),
            raw_data={"source": "coches_net", "id": "cn_005"}
        ),
        RawListing(
            source_id="cn_006",
            source="coches_net",
            title="Toyota Corolla Active Tech e-CVT",
            description="Muy buen estado general, siempre garaje.",
            url="https://www.coches.net/toyota-corolla-cn_006.aspx",
            price=23200.0,
            make="Toyota",
            model="Corolla",
            year=2021,
            mileage_km=69000,
            fuel="hybrid",
            transmission="automatic",
            location="Bilbao, ES",
            published_at=(now - timedelta(days=1)).isoformat(),
            raw_data={"source": "coches_net", "id": "cn_006"}
        ),
        RawListing(
            source_id="cn_007",
            source="coches_net",
            title="Toyota Corolla Hybrid Active",
            description="Coche como nuevo. Mantenimientos oficiales.",
            url="https://www.coches.net/toyota-corolla-cn_007.aspx",
            price=23900.0,
            make="Toyota",
            model="Corolla",
            year=2021,
            mileage_km=60000,
            fuel="hybrid",
            transmission="automatic",
            location="Madrid, ES",
            published_at=(now - timedelta(hours=18)).isoformat(),
            raw_data={"source": "coches_net", "id": "cn_007"}
        ),
        RawListing(
            source_id="cn_008",
            source="coches_net",
            title="Toyota Corolla Active Tech Hybrid",
            description="Perfecto estado, itv al dia.",
            url="https://www.coches.net/toyota-corolla-cn_008.aspx",
            price=22500.0,
            make="Toyota",
            model="Corolla",
            year=2021,
            mileage_km=78000,
            fuel="hybrid",
            transmission="automatic",
            location="Girona, ES",
            published_at=(now - timedelta(days=5)).isoformat(),
            raw_data={"source": "coches_net", "id": "cn_008"}
        ),
    ]
