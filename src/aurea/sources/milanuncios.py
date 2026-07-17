import logging
from typing import List
from datetime import datetime, timedelta
import httpx
from aurea.config import SearchConfig, load_settings
from aurea.sources.base import SourceConnector, RawListing

logger = logging.getLogger("aurea.sources.milanuncios")

class MilanunciosConnector(SourceConnector):
    name = "milanuncios"

    def collect(self, search: SearchConfig) -> List[RawListing]:
        settings = load_settings()
        results: List[RawListing] = []
        
        if not settings.scraping.use_fixtures_fallback:
            try:
                # Mock live request block to show how it fits
                headers = {"User-Agent": settings.scraping.user_agent}
                # Request Milanuncios public listing...
                pass
            except Exception as e:
                logger.warning(f"Milanuncios request failed: {e}. Falling back to fixtures.")

        fixtures = get_milanuncios_fixtures()
        
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

def get_milanuncios_fixtures() -> List[RawListing]:
    now = datetime.utcnow()
    return [
        # Fixture 1: Duplicate of WP_001 (Same Corolla, different ID/portal)
        # Used for testing deduplication between portals
        RawListing(
            source_id="ma_001",
            source="milanuncios",
            title="Toyota Corolla 1.8 Hybrid 122cv Active Tech",
            description="Toyota Corolla en perfecto estado, nacional, unico propietario. Todos los mantenimientos al dia. ITV al dia, sin averias.",
            url="https://www.milanuncios.com/toyota-de-segunda-mano/toyota-corolla-hybrid-ma_001.htm",
            price=18900.0,
            make="Toyota",
            model="Corolla",
            year=2021,
            mileage_km=72000,
            fuel="hybrid",
            transmission="automatic",
            location="Madrid, ES",
            published_at=(now - timedelta(hours=1)).isoformat(),
            raw_data={"source": "milanuncios", "id": "ma_001"}
        ),
        # Fixture 2: Another Corolla for market comparable
        RawListing(
            source_id="ma_002",
            source="milanuncios",
            title="Toyota Corolla Active Tech 2021",
            description="Buen estado general. Negociable. Particular.",
            url="https://www.milanuncios.com/toyota-de-segunda-mano/toyota-corolla-ma_002.htm",
            price=22500.0,
            make="Toyota",
            model="Corolla",
            year=2021,
            mileage_km=68000,
            fuel="hybrid",
            transmission="automatic",
            location="Barcelona, ES",
            published_at=(now - timedelta(days=2)).isoformat(),
            raw_data={"source": "milanuncios", "id": "ma_002"}
        ),
        # Fixture 3: A Hyundai i30 for general results
        RawListing(
            source_id="ma_003",
            source="milanuncios",
            title="Hyundai i30 1.0 TGDI 120cv Klass",
            description="Hyundai i30 en excelente estado. Único dueño, recién revisado.",
            url="https://www.milanuncios.com/hyundai-de-segunda-mano/hyundai-i30-ma_003.htm",
            price=15900.0,
            make="Hyundai",
            model="i30",
            year=2020,
            mileage_km=55000,
            fuel="petrol",
            transmission="manual",
            location="Castellon, ES",
            published_at=(now - timedelta(hours=5)).isoformat(),
            raw_data={"source": "milanuncios", "id": "ma_003"}
        )
    ]
