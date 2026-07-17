import re
from typing import Optional
from aurea.sources.base import RawListing
from aurea.models import Listing

def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return text.strip()

def normalize_fuel(fuel_str: Optional[str]) -> str:
    if not fuel_str:
        return "other"
    val = fuel_str.lower().strip()
    if any(x in val for x in ["gasolina", "petrol", "benzina"]):
        return "petrol"
    if any(x in val for x in ["diesel", "gasoil", "gasóleo"]):
        return "diesel"
    if any(x in val for x in ["híbrido", "hibrido", "hybrid", "mhev", "phev", "hev"]):
        return "hybrid"
    if any(x in val for x in ["eléctrico", "electrico", "electric", "bev"]):
        return "electric"
    if any(x in val for x in ["lpg", "glp"]):
        return "lpg"
    if any(x in val for x in ["cng", "gnc"]):
        return "cng"
    return "other"

def normalize_transmission(trans_str: Optional[str]) -> str:
    if not trans_str:
        return "manual"
    val = trans_str.lower().strip()
    if any(x in val for x in ["automático", "automatico", "automatic", "aut", "cvt", "dsg", "dct", "pdk"]):
        return "automatic"
    return "manual"

def extract_from_text(title: str, description: str, make: Optional[str], model: Optional[str]) -> tuple[str, str]:
    # Simple extraction helper if make/model is missing
    norm_make = make.strip() if make else ""
    norm_model = model.strip() if model else ""
    
    combined = (title + " " + description).lower()
    
    if not norm_make:
        if "toyota" in combined:
            norm_make = "Toyota"
        elif "volkswagen" in combined or "vw" in combined:
            norm_make = "Volkswagen"
        elif "peugeot" in combined:
            norm_make = "Peugeot"
        elif "ford" in combined:
            norm_make = "Ford"
        elif "subaru" in combined:
            norm_make = "Subaru"
        elif "hyundai" in combined:
            norm_make = "Hyundai"
            
    if norm_make and not norm_model:
        if norm_make.lower() == "toyota" and "corolla" in combined:
            norm_model = "Corolla"
        elif norm_make.lower() == "volkswagen" and "golf" in combined:
            norm_model = "Golf"
        elif norm_make.lower() == "peugeot" and "308" in combined:
            norm_model = "308"
        elif norm_make.lower() == "subaru" and "wrx" in combined:
            norm_model = "WRX"
        elif norm_make.lower() == "hyundai" and "i30" in combined:
            norm_model = "i30"
            
    return norm_make, norm_model

def normalize_listing(raw: RawListing) -> Listing:
    make, model = extract_from_text(raw.title, raw.description, raw.make, raw.model)
    
    # Try parsing year/mileage if missing from title/description
    year = raw.year
    if not year:
        # Regex search for years between 2000 and 2026
        match = re.search(r"\b(20[0-2][0-6])\b", raw.title)
        if match:
            year = int(match.group(1))
            
    mileage = raw.mileage_km
    if mileage is None or mileage < 0:
        mileage = 0
        
    from aurea.models import get_utc_now
    first_seen = get_utc_now()
    if raw.published_at:
        try:
            first_seen = datetime.fromisoformat(raw.published_at)
        except Exception:
            pass

    return Listing(
        source_id=raw.source_id,
        source=raw.source,
        title=normalize_text(raw.title),
        description=normalize_text(raw.description),
        url=raw.url,
        price=raw.price,
        make=make,
        model=model,
        generation=None, # will be refined in valuation if needed
        engine=None,
        year=year or 0,
        mileage_km=mileage,
        fuel=normalize_fuel(raw.fuel),
        transmission=normalize_transmission(raw.transmission),
        location=normalize_text(raw.location or "Desconocida"),
        is_active=True,
        raw_data=None, # Set from caller if needed
        is_aurea=False,
        rating=0.0,
        first_seen_at=first_seen,
        last_seen_at=first_seen
    )
