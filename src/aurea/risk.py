import re
from aurea.models import Listing
from aurea.market import MarketAnalysis

def calculate_risk(listing: Listing, market: MarketAnalysis) -> float:
    """
    Calculates a risk score from 0 to 100.
    A score above 15/100 prevents classification as AUREA.
    """
    risk_score = 0.0
    combined = f"{listing.title} {listing.description}".lower()

    # 1. Price-based risks
    if market.expected_price > 0:
        pct_of_market = listing.price / market.expected_price
        # An abnormally low price (e.g. under 60%) points to scam/hidden issues
        if pct_of_market < 0.65:
            risk_score += 40.0
        elif pct_of_market < 0.75:
            risk_score += 20.0
        elif pct_of_market < 0.82:
            risk_score += 10.0

    # 2. Text/keyword risk indicators
    # Import risk
    if any(w in combined for w in ["importado", "importación", "traído de", "alemania", "francia", "belgica", "matrícula nueva"]):
        if not any(w in combined for w in ["historial completo", "libro de revisiones", "nacional"]):
            risk_score += 15.0  # Import without documented history

    # Repair or damage keywords (minor enough to pass the filters, e.g., scratch, paint, minor dent)
    if any(w in combined for w in ["roce", "rayajo", "arañazo", "desperfecto", "desgaste", "bollo", "chapa", "pintar"]):
        risk_score += 5.0

    # Warranty risk
    if any(w in combined for w in ["sin garantía", "sin garantia", "garantía aparte", "garantia aparte"]):
        risk_score += 12.0

    # 3. Data inconsistency (e.g. year/mileage mismatch)
    # Extremely low mileage for its age (e.g. under 3000 km per year for a car over 5 years old)
    age_years = datetime_now_year() - listing.year
    if age_years > 5 and listing.mileage_km > 0:
        km_per_year = listing.mileage_km / age_years
        if km_per_year < 2000:
            risk_score += 15.0  # Suspiciously low mileage (km rewinding risk)

    # 4. Duplicate photos/text hints
    if any(w in combined for w in ["foto orientativa", "fotos de archivo", "no contractual"]):
        risk_score += 10.0

    return min(100.0, risk_score)

def datetime_now_year() -> int:
    import datetime
    return datetime.datetime.now().year
