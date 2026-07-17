import re
import math
import logging
from datetime import datetime, timedelta
from typing import Optional
from aurea.models import Listing
from aurea.config import SearchConfig

logger = logging.getLogger("aurea.filters")

CITIES_COORDINATES = {
    "rute": (37.3259, -4.3683),
    "malaga": (36.7213, -4.4214),
    "cordoba": (37.8882, -4.7794),
    "lucena": (37.3995, -4.4842),
    "cabra": (37.4719, -4.4421),
    "priego de cordoba": (37.4385, -4.1950),
    "iznajar": (37.2568, -4.3117),
    "loja": (37.1664, -4.1523),
    "antequera": (37.0184, -4.5601),
    "sevilla": (37.3891, -5.9845),
    "granada": (37.1773, -3.5986),
    "madrid": (40.4168, -3.7038),
    "barcelona": (41.3851, 2.1734),
    "valencia": (39.4699, -0.3763),
    "murcia": (37.9922, -1.1307),
    "gijon": (43.5357, -5.6615),
    "bilbao": (43.2630, -2.9350),
    "zaragoza": (41.6488, -0.8891),
    "girona": (41.9794, 2.8214),
    "alicante": (38.3452, -0.4810),
}

def get_distance_km(loc1_name: str, loc2_name: str, session=None) -> Optional[float]:
    def clean(name: str) -> str:
        name = name.lower()
        for acc, pln in [('á','a'), ('é','e'), ('í','i'), ('ó','o'), ('ú','u'), ('ü','u'), ('ñ','n')]:
            name = name.replace(acc, pln)
        return name.strip()
        
    def get_coords(name: str) -> Optional[tuple[float, float]]:
        cleaned = clean(name)
        # 1. Check pre-defined dictionary
        for k, v in CITIES_COORDINATES.items():
            if k in cleaned:
                return v
                
        # 2. Check DB / Nominatim cache if session is provided
        if session:
            city_part = cleaned.split(",")[0].strip()
            if not city_part:
                return None
                
            from sqlmodel import select
            from aurea.models import LocationCoordinate
            
            stmt = select(LocationCoordinate).where(LocationCoordinate.name == city_part)
            try:
                cached = session.exec(stmt).first()
                if cached:
                    return (cached.latitude, cached.longitude)
            except Exception as e:
                logger.error(f"Error reading coordinates from cache: {e}")
                
            # If not in cache, query Nominatim
            import httpx
            url = "https://nominatim.openstreetmap.org/search"
            headers = {"User-Agent": "Aurea-CarFinding/1.0 (antigravity@google.com)"}
            params = {"q": f"{city_part}, Spain", "format": "json", "limit": 1}
            try:
                r = httpx.get(url, headers=headers, params=params, timeout=5)
                if r.status_code == 200 and r.json():
                    data = r.json()[0]
                    lat = float(data["lat"])
                    lon = float(data["lon"])
                    
                    # Cache it
                    try:
                        coord = LocationCoordinate(name=city_part, latitude=lat, longitude=lon)
                        session.add(coord)
                        session.commit()
                        logger.info(f"Geocoded and cached coordinates for '{city_part}': ({lat}, {lon})")
                        return (lat, lon)
                    except Exception as e:
                        logger.error(f"Error caching coordinates: {e}")
                        return (lat, lon)
            except Exception as e:
                logger.error(f"Error geocoding {city_part}: {e}")
                
        return None

    c1 = get_coords(loc1_name)
    c2 = get_coords(loc2_name)
    
    if not c1 or not c2:
        return None
        
    lat1, lon1 = c1
    lat2, lon2 = c2
    R = 6371.0 # Radius of Earth in km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def has_negated_keyword(text: str, keywords: list[str], negation_words: list[str]) -> bool:
    text = text.lower()
    for kw in keywords:
        # Use word boundaries
        matches = list(re.finditer(r'\b' + re.escape(kw) + r'\b', text))
        for m in matches:
            # Check preceding context (up to 30 chars) for negation
            start = max(0, m.start() - 30)
            precedent = text[start:m.start()]
            
            # If a negation word is found near, we consider this instance negated
            negation_pattern = r'\b(' + '|'.join(re.escape(w) for w in negation_words) + r')\b'
            if re.search(negation_pattern, precedent):
                continue
            
            return True
    return False

def is_damaged(listing: Listing) -> bool:
    keywords = [
        "averia", "averias", "averiado", "averiada", "roto", "rota", "fallo", "fallos",
        "reparar", "para reparar", "culata", "junta culata", "motor roto", "despiece",
        "piezas", "para piezas", "accidentado", "golpe", "siniestro", "dañado", "daño"
    ]
    negation_words = ["no", "sin", "ningun", "ninguna", "libre", "cero", "nunca", "limpio"]
    combined = f"{listing.title} {listing.description}"
    return has_negated_keyword(combined, keywords, negation_words)

def is_financed(listing: Listing) -> bool:
    # Check for monthly payment lookalikes
    # If the price is extremely low (e.g., < 1000) and the title/description mentions 'mes' or 'cuota', it is a cuota
    combined = f"{listing.title} {listing.description}".lower()
    
    # 1. Price is suspiciously low (e.g., < 600 EUR) and mentions monthly context
    if listing.price < 600.0:
        if any(w in combined for w in ["mes", "cuota", "al mes", "renting", "leasing"]):
            return True
            
    # 2. Keywords indicating mandatory financing
    keywords = ["financiar", "financiado", "financiacion", "sujeto a", "obligatorio financiar", "descuento por financiar"]
    negation_words = ["no", "sin", "contado", "no sujeto"]
    return has_negated_keyword(combined, keywords, negation_words)

def is_no_itv_or_docs(listing: Listing) -> bool:
    keywords = ["sin itv", "itv caducada", "itv desfavorable", "sin papeles", "sin documentacion", "documentacion perdida", "documentación perdida"]
    negation_words = ["no", "pasada", "itv al dia", "itv al día"]
    combined = f"{listing.title} {listing.description}"
    return has_negated_keyword(combined, keywords, negation_words)

def is_professional_only(listing: Listing) -> bool:
    keywords = ["solo profesionales", "profesionales", "autonomos", "para profesionales", "sin garantia", "sin garantía"]
    negation_words = ["no", "particular", "particulares"]
    combined = f"{listing.title} {listing.description}"
    return has_negated_keyword(combined, keywords, negation_words)

def is_auction_or_embargo(listing: Listing) -> bool:
    keywords = ["subasta", "embargo", "embargado", "puja", "pujas", "embargados"]
    negation_words = ["no", "sin", "libre"]
    combined = f"{listing.title} {listing.description}"
    return has_negated_keyword(combined, keywords, negation_words)

def pre_filter_listing(listing: Listing, search: SearchConfig, session=None) -> tuple[bool, str]:
    """
    Evaluates basic filter rules.
    Returns (keep, reason_for_discard)
    """
    # 1. Basic properties
    if not listing.url:
        return False, "Sin enlace activo"
        
    if listing.price <= 0:
        return False, "Sin precio real"
        
    if not listing.make:
        listing.make = "Vehículo"
    if not listing.model:
        listing.model = "Genérico"
        
    if not listing.year or listing.year < 1900:
        return False, "Sin año válido"
        
    if listing.mileage_km is None:
        return False, "Sin kilometraje"

    # Location places check
    if search.location.places:
        def clean_text(t: str) -> str:
            t = t.lower()
            for acc, pln in [('á','a'), ('é','e'), ('í','i'), ('ó','o'), ('ú','u'), ('ü','u'), ('ñ','n')]:
                t = t.replace(acc, pln)
            return t.strip()

        # If a radius is specified, check the distance
        if search.location.radius_km is not None:
            center_place = search.location.places[0]
            dist = get_distance_km(center_place, listing.location, session=session)
            if dist is not None:
                if dist > search.location.radius_km:
                    return False, f"Fuera del radio de {search.location.radius_km} km (distancia: {dist:.1f} km)"
            else:
                # Fallback to place substring match if coordinates are not available
                loc_match = False
                listing_loc = clean_text(listing.location) if listing.location else ""
                for place in search.location.places:
                    if clean_text(place) in listing_loc:
                        loc_match = True
                        break
                if not loc_match:
                    return False, f"Ubicación no deseada (no coincide con el centro): {listing.location}"
        else:
            # Traditional place substring match
            loc_match = False
            listing_loc = clean_text(listing.location) if listing.location else ""
            for place in search.location.places:
                if clean_text(place) in listing_loc:
                    loc_match = True
                    break
            if not loc_match:
                return False, f"Ubicación no deseada: {listing.location}"

    # 2. Exclude sold or reserved
    combined = f"{listing.title} {listing.description}".lower()
    if any(w in combined for w in ["vendido", "reservado", "ya no disponible"]):
        return False, "Vendido o reservado"

    # 3. Time limit (Configurable age in days, defaults to 30)
    max_age = search.vehicle.max_age_days if search.vehicle.max_age_days is not None else 30
    if listing.first_seen_at:
        from datetime import timezone
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        age_days = (now_utc - listing.first_seen_at).days
        if age_days > max_age:
            return False, f"Con más de {max_age} días"

    # 4. Exclusions Config
    exc = search.exclusions
    
    if exc.damaged or exc.mechanical_failure:
        if is_damaged(listing):
            return False, "Avería o averiado"
            
    if exc.financing_price:
        if is_financed(listing):
            return False, "Precio financiado / cuota"
            
    if exc.no_itv:
        if is_no_itv_or_docs(listing):
            return False, "Sin ITV o documentación"
            
    if exc.professional_only:
        if is_professional_only(listing):
            return False, "Solo para profesionales"
            
    if exc.auction:
        if is_auction_or_embargo(listing):
            return False, "Subasta o embargo"
            
    return True, ""
