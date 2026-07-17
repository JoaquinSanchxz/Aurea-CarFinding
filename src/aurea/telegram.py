import logging
import httpx
from aurea.config import load_settings
from aurea.models import Listing, Evaluation

logger = logging.getLogger("aurea.telegram")

def format_parts_availability(score: float) -> str:
    if score >= 85:
        return "alta disponibilidad"
    if score >= 70:
        return "disponibilidad normal"
    return "repuestos escasos"

def format_maintenance(score: float) -> str:
    if score >= 80:
        return "económico"
    if score >= 65:
        return "razonable"
    return "costoso"

def format_efficiency(score: float) -> str:
    if score >= 80:
        return "favorable"
    if score >= 65:
        return "moderado"
    return "alto"

def format_resale(score: float) -> str:
    if score >= 85:
        return "alta"
    if score >= 70:
        return "media"
    return "baja"

def format_telegram_message(listing: Listing, eval_data: Evaluation) -> str:
    # Build reasons
    reasons_str = ""
    for r in eval_data.reasons.split(","):
        if r.strip():
            reasons_str += f"✅ {r.strip()}\n"
            
    # Build warnings
    warnings_str = ""
    for w in eval_data.warnings.split(","):
        if w.strip():
            warnings_str += f"⚠️ {w.strip()}\n"

    # Map scores to labels
    parts_label = format_parts_availability(eval_data.parts_availability_score)
    maint_label = format_maintenance(eval_data.maintenance_score)
    eff_label = format_efficiency(eval_data.efficiency_score)
    resale_label = format_resale(eval_data.resale_score)

    rating_str = f"{int(listing.rating)}/10" if listing.rating else "10/10"
    msg = f"""🏆 AUREA — OPORTUNIDAD {rating_str}

{listing.make} {listing.model} {listing.year}
{listing.year} · {listing.mileage_km:,} km · {"Automático" if listing.transmission == "automatic" else "Manual"}
{listing.price:,.0f} €

Valor estimado: {eval_data.saving_eur + listing.price:,.0f} €
Ahorro ajustado: {eval_data.adjusted_saving_eur:,.0f} € — {eval_data.discount_percent}%
Comparables: {eval_data.num_comparables}
Confianza: {int(eval_data.market_confidence * 100)}%
Riesgo: {int(eval_data.risk_score)}/100

Fiabilidad: {int(eval_data.reliability_score)}/100
Repuestos: {parts_label}
Mantenimiento: {maint_label}
Consumo: {eff_label}
Reventa: {resale_label}

Por qué destaca:
{reasons_str.strip()}

Revisar:
{warnings_str.strip()}

Fuente: {listing.source.capitalize()}
🔗 {listing.url}

ID: {listing.opportunity_id}"""
    return msg

def send_telegram_alert(listing: Listing, eval_data: Evaluation) -> bool:
    settings = load_settings()
    bot_token = settings.telegram.bot_token
    chat_id = settings.telegram.chat_id
    
    if not bot_token or not chat_id:
        logger.error("Telegram credentials missing in settings.")
        return False
        
    msg = format_telegram_message(listing, eval_data)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": msg,
        "disable_web_page_preview": False
    }
    
    try:
        r = httpx.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            logger.info(f"Telegram notification sent successfully for {listing.opportunity_id}")
            return True
        else:
            logger.error(f"Failed to send Telegram notification. Status: {r.status_code}, Response: {r.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram notification connection error: {e}")
        return False

def send_test_message() -> bool:
    settings = load_settings()
    bot_token = settings.telegram.bot_token
    chat_id = settings.telegram.chat_id
    
    if not bot_token or not chat_id:
        logger.error("Telegram credentials missing in settings.")
        return False
        
    msg = "🔔 Aurea: Mensaje de prueba de la API del bot de Telegram. Conexión correcta."
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": msg
    }
    
    try:
        r = httpx.post(url, json=payload, timeout=15)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"Telegram test connection error: {e}")
        return False
