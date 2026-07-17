import logging
from datetime import datetime
from typing import Dict, List, Any
from sqlmodel import Session, select, func

from aurea.config import load_settings, load_searches, SearchConfig
from aurea.database import get_session, init_db
from aurea.sources.wallapop import WallapopConnector
from aurea.sources.milanuncios import MilanunciosConnector
from aurea.sources.coches_net import CochesNetConnector
from aurea.normalizer import normalize_listing
from aurea.filters import pre_filter_listing
from aurea.deduplication import process_duplicates_and_persist
from aurea.market import analyze_market
from aurea.risk import calculate_risk
from aurea.scoring import evaluate_listing, is_aurea_opportunity
from aurea.telegram import send_telegram_alert
from aurea.models import Listing, Evaluation, Notification, get_utc_now

logger = logging.getLogger("aurea.pipeline")

def double_validate_opportunity(session: Session, listing: Listing, eval_data: Evaluation, search: SearchConfig) -> bool:
    """
    Executes the double validation steps on potential AUREA opportunities before notifying.
    """
    logger.info(f"Running double validation for potential AUREA: {listing.title}")
    
    # 1. Confirma que sigue activo
    if not listing.is_active:
        return False
        
    # 2. Confirma el precio (no sea descabellado o cambiado)
    if listing.price <= 0:
        return False
        
    # 3. Confirma que no es financiación ni cuota
    combined = f"{listing.title} {listing.description}".lower()
    if listing.price < 600.0 and any(w in combined for w in ["mes", "cuota", "al mes"]):
        return False
        
    # 4. Re-check exclusions
    if any(w in combined for w in ["averia", "motor roto", "culata"]):
        return False
        
    # 5. Recheck overall score and adjusted savings (respecting custom search thresholds)
    min_saving = search.price.minimum_adjusted_saving_eur if search.price.minimum_adjusted_saving_eur is not None else 3000.0
    required_rating = search.alerting.required_rating if (search and search.alerting) else 10
    min_global = 95.0 if required_rating >= 10 else 90.0
    
    if eval_data.score_global < min_global or eval_data.adjusted_saving_eur < min_saving:
        return False
        
    return True

def run_pipeline() -> Dict[str, int]:
    # Initialize DB
    init_db()
    session = get_session()
    
    summary = {
        "encontrados": 0,
        "nuevos": 0,
        "descartados": 0,
        "analizados": 0,
        "candidatos": 0,
        "aurea": 0,
        "alertas_enviadas": 0
    }
    
    # Process Telegram commands to update searches.yaml dynamically
    try:
        from aurea.telegram import process_telegram_commands
        process_telegram_commands(session)
    except Exception as e:
        logger.error(f"Error processing Telegram commands: {e}")
    
    searches = load_searches()
    if not searches:
        logger.warning("No searches configured or enabled.")
        return summary
        
    connectors = [
        WallapopConnector(),
        MilanunciosConnector(),
        CochesNetConnector()
    ]
    
    # Step 1: Collect raw listings from all sources
    raw_listings = []
    for search in searches:
        if not search.enabled:
            continue
        for conn in connectors:
            try:
                collected = conn.collect(search)
                logger.info(f"Recopilados {len(collected)} anuncios de {conn.name}")
                summary["encontrados"] += len(collected)
                raw_listings.extend(collected)
            except Exception as e:
                logger.error(f"Error collecting from {conn.name}: {e}")
                
    # Sort collected raw listings by publication date (newest first)
    raw_listings.sort(key=lambda x: x.published_at or "", reverse=True)
                
    # Step 2: Normalize and pre-filter
    valid_listings: List[Listing] = []
    for raw in raw_listings:
        try:
            listing = normalize_listing(raw)
            # Fetch active search config (using the first one for this simplified pipeline)
            search = searches[0]
            keep, discard_reason = pre_filter_listing(listing, search, session=session)
            if keep:
                logger.info(f"VISTO [OK]: {listing.source.upper()} | {listing.make} {listing.model} | {listing.price}€ | {listing.year} | {listing.mileage_km}km | {listing.location}")
                valid_listings.append(listing)
            else:
                summary["descartados"] += 1
                logger.info(f"VISTO [DESCARTADO]: {listing.source.upper()} | {listing.title} ({listing.price}€) -> {discard_reason}")
        except Exception as e:
            summary["descartados"] += 1
            logger.error(f"Error normalizing listing: {e}")
            
    # Step 3: Deduplicate and persist
    # Process duplicates merges active records, tracks price updates, and returns unique new/updated elements
    unique_listings = process_duplicates_and_persist(session, valid_listings)
    summary["nuevos"] = len(unique_listings)
    
    # Step 4: Run market analysis, risk analysis, and scoring
    for listing in unique_listings:
        try:
            search = searches[0]
            
            # Recalculate market stats (using existing database active records)
            market_stats = analyze_market(session, listing)
            risk = calculate_risk(listing, market_stats)
            eval_data = evaluate_listing(listing, market_stats, risk, search=search)
            
            # Save evaluation
            eval_data.listing_id = listing.id
            session.add(eval_data)
            session.commit()
            
            summary["analizados"] += 1
            logger.info(f"ANALIZADO: {listing.make} {listing.model} ({listing.year}) | Precio: {listing.price}€ | Score Global: {eval_data.score_global}/100 | Riesgo: {eval_data.risk_score}/100")
            
            # Check Aurea eligibility
            is_aurea = is_aurea_opportunity(listing, eval_data, search)
            if is_aurea:
                summary["candidatos"] += 1
                
                # Double validation
                if double_validate_opportunity(session, listing, eval_data, search):
                    # Check if already notified to avoid duplicates
                    notified_stmt = select(Notification).where(
                        Notification.listing_id == listing.id,
                        Notification.status == "sent"
                    )
                    already_notified = session.exec(notified_stmt).first()
                    
                    # Generate opportunity ID if not set
                    if not listing.opportunity_id:
                        max_id_stmt = select(Listing.opportunity_id).where(Listing.opportunity_id != None)
                        existing_ids = session.exec(max_id_stmt).all()
                        next_num = len(existing_ids) + 1
                        listing.opportunity_id = f"AU-{next_num:06d}"
                    
                    listing.is_aurea = True
                    listing.rating = 10.0 if eval_data.score_global >= 95.0 else 9.0
                    session.add(listing)
                    session.commit()
                    
                    summary["aurea"] += 1
                    logger.warning(f"¡NUEVA OPORTUNIDAD AUREA DETECTADA! {listing.make} {listing.model} - Puntuación: {listing.rating}/10 - Ahorro: {eval_data.adjusted_saving_eur}€")
                    
                    if not already_notified:
                        # Attempt to notify
                        success = send_telegram_alert(listing, eval_data)
                        
                        notification = Notification(
                            listing_id=listing.id,
                            opportunity_id=listing.opportunity_id,
                            sent_at=get_utc_now(),
                            status="sent" if success else "failed",
                            error_message=None if success else "Telegram post failed"
                        )
                        session.add(notification)
                        session.commit()
                        
                        if success:
                            summary["alertas_enviadas"] += 1
                    else:
                        logger.info(f"Opportunity {listing.opportunity_id} already notified. Skipping alert.")
            else:
                # Update listing rating / Aurea state to false if it doesn't qualify anymore
                listing.is_aurea = False
                listing.rating = round(eval_data.score_global / 10.0, 1)
                session.add(listing)
                session.commit()
                
        except Exception as e:
            logger.error(f"Error evaluating listing {listing.id}: {e}")
            
    session.close()
    
    if summary["alertas_enviadas"] == 0:
        try:
            from aurea.telegram import send_heartbeat_message
            send_heartbeat_message(summary)
        except Exception as e:
            logger.error(f"Error sending Telegram heartbeat: {e}")
            
    return summary

def retry_failed_notifications():
    """
    Scans for failed notifications in the database and retries sending them.
    """
    session = get_session()
    stmt = select(Notification).where(Notification.status == "failed")
    failed = session.exec(stmt).all()
    
    for notif in failed:
        listing = session.get(Listing, notif.listing_id)
        if not listing:
            continue
            
        # Get latest evaluation
        eval_stmt = select(Evaluation).where(Evaluation.listing_id == listing.id).order_by(Evaluation.evaluated_at.desc())
        eval_data = session.exec(eval_stmt).first()
        if not eval_data:
            continue
            
        success = send_telegram_alert(listing, eval_data)
        if success:
            notif.status = "sent"
            notif.sent_at = get_utc_now()
            notif.error_message = None
            session.add(notif)
            session.commit()
            logger.info(f"Retried and sent notification for {listing.opportunity_id} successfully.")
            
    session.close()
