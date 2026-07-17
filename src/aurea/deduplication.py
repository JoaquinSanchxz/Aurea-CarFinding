import re
import logging
from typing import List, Optional
from sqlmodel import Session, select
from aurea.models import Listing, PriceHistory

logger = logging.getLogger("aurea.deduplication")

def are_listings_equivalent(l1: Listing, l2: Listing) -> bool:
    """
    Checks if two listings represent the same physical vehicle.
    """
    if not l1.make or not l2.make or l1.make.lower() != l2.make.lower():
        return False
    if not l1.model or not l2.model or l1.model.lower() != l2.model.lower():
        return False
    if l1.year != l2.year:
        return False
        
    # Location check (different cities mean different physical vehicles)
    if l1.location and l2.location:
        loc1 = l1.location.lower().split(",")[0].strip()
        loc2 = l2.location.lower().split(",")[0].strip()
        if loc1 and loc2 and loc1 != loc2:
            return False
    
    # Mileage difference: within 1500 km or 3%
    mileage_diff = abs(l1.mileage_km - l2.mileage_km)
    if mileage_diff > 1500:
        pct_diff = mileage_diff / max(1, l1.mileage_km)
        if pct_diff > 0.03:
            return False
            
    # Price difference: within 1500 EUR or 6%
    price_diff = abs(l1.price - l2.price)
    if price_diff > 1500:
        pct_diff = price_diff / max(1, l1.price)
        if pct_diff > 0.06:
            return False

    # Check description text overlap
    words1 = set(re.findall(r'\w+', l1.description.lower()))
    words2 = set(re.findall(r'\w+', l2.description.lower()))
    # filter out words under 4 chars
    words1 = {w for w in words1 if len(w) > 4}
    words2 = {w for w in words2 if len(w) > 4}
    
    if not words1 or not words2:
        # Fall back to title match
        return l1.title.lower() == l2.title.lower()
        
    overlap = words1.intersection(words2)
    # If they share at least 5 long words, or share 40% of their words
    if len(overlap) >= 5 or len(overlap) / min(len(words1), len(words2)) > 0.4:
        return True

    return False

def process_duplicates_and_persist(session: Session, new_listings: List[Listing]) -> List[Listing]:
    """
    Compares new listings against existing database listings.
    Saves price changes, updates last_seen_at, and returns unique listings to analyze.
    """
    # Fetch all active listings from the DB
    stmt = select(Listing).where(Listing.is_active == True)
    existing_listings = session.exec(stmt).all()
    
    processed_listings: List[Listing] = []
    
    for new_l in new_listings:
        # Check against existing listings in the database
        duplicate_found: Optional[Listing] = None
        for ext_l in existing_listings:
            if ext_l.source_id == new_l.source_id and ext_l.source == new_l.source:
                duplicate_found = ext_l
                break
            if are_listings_equivalent(ext_l, new_l):
                duplicate_found = ext_l
                break
                
        # Check against already processed listings in this run (e.g. portal duplicates)
        if not duplicate_found:
            for prc_l in processed_listings:
                if are_listings_equivalent(prc_l, new_l):
                    duplicate_found = prc_l
                    break
        
        if duplicate_found:
            # We found a duplicate. Merge details and record price updates.
            logger.info(f"Duplicate/republication found: {new_l.title} (Source ID: {new_l.source_id}) maps to DB ID: {duplicate_found.id}")
            
            # If price changed, save history
            if abs(duplicate_found.price - new_l.price) > 0.01:
                hist = PriceHistory(listing_id=duplicate_found.id, price=duplicate_found.price)
                session.add(hist)
                logger.info(f"Price change detected for {duplicate_found.title}: {duplicate_found.price} -> {new_l.price}")
                
                # If price dropped, allow re-notifying by clearing old notification status
                if new_l.price < duplicate_found.price:
                    from sqlmodel import text
                    try:
                        session.execute(
                            text("UPDATE notification SET status = 'superseded_by_price_drop' WHERE listing_id = :id"),
                            {"id": duplicate_found.id}
                        )
                    except Exception as e:
                        logger.error(f"Error updating old notifications: {e}")
                
                duplicate_found.price = new_l.price
                processed_listings.append(duplicate_found)
                
            duplicate_found.last_seen_at = new_l.last_seen_at
            
            # Update description if new is more complete
            if len(new_l.description) > len(duplicate_found.description):
                duplicate_found.description = new_l.description
                duplicate_found.title = new_l.title
                
            # If new listing url is different, we can append it or keep the original.
            # We'll just preserve the original as the main one, but write a log.
            session.add(duplicate_found)
        else:
            # New unique listing
            session.add(new_l)
            session.commit() # commit to generate ID
            
            # Record initial price in history
            hist = PriceHistory(listing_id=new_l.id, price=new_l.price)
            session.add(hist)
            processed_listings.append(new_l)
            
    session.commit()
    return processed_listings
