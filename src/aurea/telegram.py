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

def send_heartbeat_message(summary: dict) -> bool:
    settings = load_settings()
    bot_token = settings.telegram.bot_token
    chat_id = settings.telegram.chat_id
    
    if not bot_token or not chat_id:
        logger.error("Telegram credentials missing in settings.")
        return False
        
    msg = f"""🔍 *Aurea está activo y buscando*
No se han encontrado nuevas ofertas de vehículos en esta búsqueda.

📊 *Resumen de la búsqueda:*
• Encontrados en portales: {summary.get('encontrados', 0)}
• Nuevos/analizados: {summary.get('nuevos', 0)}
• Descartados por filtros: {summary.get('descartados', 0)}
• Candidatos potenciales: {summary.get('candidatos', 0)}
• Nuevas ofertas Aurea: {summary.get('aurea', 0)}

El sistema sigue activo y monitorizando en segundo plano."""

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown"
    }
    
    try:
        r = httpx.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            logger.info("Telegram heartbeat notification sent successfully.")
            return True
        else:
            logger.error(f"Failed to send Telegram heartbeat. Status: {r.status_code}, Response: {r.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram heartbeat connection error: {e}")
        return False


def process_telegram_commands(session) -> None:
    import yaml
    from aurea.config import load_settings, PROJECT_ROOT
    from sqlmodel import text
    
    settings = load_settings()
    token = settings.telegram.bot_token
    chat_id = settings.telegram.chat_id
    
    if not token or not chat_id:
        logger.warning("Telegram credentials not configured. Skipping command processing.")
        return
        
    try:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS botstate (
                key VARCHAR PRIMARY KEY,
                value VARCHAR
            )
        """))
        session.commit()
    except Exception as e:
        logger.error(f"Error creating botstate table: {e}")
        
    # Get last update_id
    try:
        state_stmt = text("SELECT value FROM botstate WHERE key = 'last_update_id'")
        row = session.execute(state_stmt).first()
        last_update_id = int(row[0]) if row else -1
    except Exception as e:
        logger.error(f"Error fetching last_update_id: {e}")
        last_update_id = -1
        
    offset = last_update_id + 1
    
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"offset": offset, "timeout": 1}
    
    try:
        r = httpx.get(url, params=params, timeout=10)
        if r.status_code != 200:
            logger.error(f"Error getting Telegram updates: {r.status_code}")
            return
        updates = r.json().get("result", [])
    except Exception as e:
        logger.error(f"Error connecting to Telegram getUpdates: {e}")
        return
        
    if not updates:
        return
        
    searches_file = PROJECT_ROOT / "config" / "searches.yaml"
    if not searches_file.exists():
        logger.error(f"searches.yaml not found at {searches_file}")
        return
        
    with open(searches_file, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f) or {}
        
    modified = False
    new_last_update_id = last_update_id
    
    for update in updates:
        update_id = update.get("update_id")
        if update_id is not None:
            new_last_update_id = max(new_last_update_id, update_id)
            
        message = update.get("message")
        if not message:
            continue
            
        sender_chat_id = str(message.get("chat", {}).get("id"))
        if sender_chat_id != str(chat_id):
            logger.warning(f"Ignored message from unauthorized chat: {sender_chat_id}")
            continue
            
        text_content = message.get("text", "").strip()
        if not text_content.startswith("/"):
            continue
            
        parts = text_content.split()
        command = parts[0].lower()
        args = parts[1:]
        
        reply = None
        
        if command in ["/ayuda", "/help", "/start"]:
            reply = """🤖 *Comandos Aurea:*
• `/status` - Configuración actual y estadísticas.
• `/presupuesto <valor>` - Presupuesto máximo (ej: `/presupuesto 10000`).
• `/localizacion <lugar> <radio>` - Centro y radio en km (ej: `/localizacion Rute 50`).
• `/min_rating <valor>` - Nota mínima requerida (ej: `/min_rating 9` o `10`).
• `/combustible <tipos>` - Combustibles separados por coma (ej: `/combustible diesel,hybrid`).
• `/marca <marcas>` - Marcas a buscar (ej: `/marca volkswagen`). Use `/marca reset` para cualquiera.
• `/modelo <modelos>` - Modelos a buscar (ej: `/modelo golf`). Use `/modelo reset` para cualquiera.
• `/kilometraje <valor>` / `/km <valor>` - Kilometraje máximo (ej: `/km 120000`).
• `/ano <valor>` / `/year <valor>` - Año mínimo (ej: `/ano 2012`).
• `/analizar` - Fuerza la ejecución inmediata de la búsqueda.
"""
        elif command == "/status":
            try:
                total_listings = session.execute(text("SELECT count(*) FROM listing")).first()[0]
                total_aurea = session.execute(text("SELECT count(*) FROM listing WHERE is_aurea = 1")).first()[0]
            except Exception:
                total_listings = 0
                total_aurea = 0
            
            search_item = config_data.get("searches", [{}])[0]
            max_price = search_item.get("price", {}).get("max_price_eur", "No def")
            places = ", ".join(search_item.get("location", {}).get("places", []))
            radius = search_item.get("location", {}).get("radius_km", "No def")
            req_rating = search_item.get("alerting", {}).get("required_rating", 10)
            fuels = ", ".join(search_item.get("vehicle", {}).get("fuels", [])) or "Cualquiera"
            pref_fuels = ", ".join(search_item.get("vehicle", {}).get("preferred_fuels", [])) or "Ninguno"
            makes = ", ".join(search_item.get("vehicle", {}).get("makes", [])) or "Cualquiera"
            models = ", ".join(search_item.get("vehicle", {}).get("models", [])) or "Cualquiera"
            max_km = search_item.get("vehicle", {}).get("max_mileage_km", "No def")
            min_year = search_item.get("vehicle", {}).get("min_year", "No def")
            
            # Format max_km with thousand separator
            max_km_str = f"{max_km:,} km" if isinstance(max_km, int) else str(max_km)
            
            reply = f"""📊 *Estado de Aurea:*
• *Presupuesto Máximo:* {max_price}€
• *Ubicación:* {places.capitalize()} (Radio: {radius} km)
• *Nota Mínima:* {req_rating}/10
• *Combustibles:* {fuels}
• *Preferidos:* {pref_fuels}
• *Marcas:* {makes}
• *Modelos:* {models}
• *Kilometraje Máximo:* {max_km_str}
• *Año Mínimo:* {min_year}
• *Total coches en BD:* {total_listings}
• *Oportunidades encontradas:* {total_aurea}
"""
        elif command in ["/presupuesto", "/set_budget"]:
            if not args:
                reply = "⚠️ Por favor, especifica un valor numérico. Ej: `/presupuesto 10000`"
            else:
                try:
                    val = float(args[0])
                    for s in config_data.get("searches", []):
                        if "price" not in s:
                            s["price"] = {}
                        s["price"]["max_price_eur"] = int(val)
                    modified = True
                    reply = f"✅ ¡Presupuesto máximo actualizado a *{int(val)}€*!"
                except ValueError:
                    reply = "⚠️ El presupuesto debe ser un número entero."
                    
        elif command in ["/localizacion", "/set_location"]:
            if len(args) < 2:
                reply = "⚠️ Especifica lugar y radio en km. Ej: `/localizacion Rute 50`"
            else:
                lugar = args[0]
                try:
                    radio = int(args[1])
                    for s in config_data.get("searches", []):
                        if "location" not in s:
                            s["location"] = {}
                        s["location"]["places"] = [lugar.lower()]
                        s["location"]["radius_km"] = radio
                    modified = True
                    reply = f"✅ ¡Ubicación actualizada a *{lugar.capitalize()}* con un radio de *{radio} km*!"
                except ValueError:
                    reply = "⚠️ El radio debe ser un número entero en km."
                    
        elif command == "/min_rating":
            if not args:
                reply = "⚠️ Especifica la nota mínima requerida. Ej: `/min_rating 9`"
            else:
                try:
                    val = int(args[0])
                    if val not in [9, 10]:
                        reply = "⚠️ La nota mínima debe ser 9 o 10."
                    else:
                        for s in config_data.get("searches", []):
                            if "alerting" not in s:
                                s["alerting"] = {}
                            s["alerting"]["required_rating"] = val
                        modified = True
                        reply = f"✅ ¡Nota mínima requerida actualizada a *{val}/10*!"
                except ValueError:
                    reply = "⚠️ La nota debe ser un número entero."
                    
        elif command in ["/combustible", "/set_fuel"]:
            if not args:
                reply = "⚠️ Especifica los combustibles (ej: `/combustible diesel` o `/combustible diesel,hybrid`)."
            else:
                fuels_list = [f.strip().lower() for f in args[0].split(",") if f.strip()]
                for s in config_data.get("searches", []):
                    if "vehicle" not in s:
                        s["vehicle"] = {}
                    s["vehicle"]["fuels"] = fuels_list
                modified = True
                reply = f"✅ ¡Combustibles de búsqueda actualizados a: *{', '.join(fuels_list)}*!"
                
        elif command in ["/marca", "/make"]:
            if not args:
                reply = "⚠️ Especifica las marcas (ej: `/marca volkswagen,toyota`). Escribe `/marca reset` para buscar cualquier marca."
            else:
                raw_val = " ".join(args)
                if raw_val.lower().strip() == "reset":
                    makes_list = []
                    reply_text = "cualquier marca"
                else:
                    makes_list = [m.strip().capitalize() for m in raw_val.split(",") if m.strip()]
                    reply_text = ", ".join(makes_list)
                for s in config_data.get("searches", []):
                    if "vehicle" not in s:
                        s["vehicle"] = {}
                    s["vehicle"]["makes"] = makes_list
                modified = True
                reply = f"✅ ¡Marcas de búsqueda actualizadas a: *{reply_text}*!"
                
        elif command in ["/modelo", "/model"]:
            if not args:
                reply = "⚠️ Especifica los modelos (ej: `/modelo golf,corolla`). Escribe `/modelo reset` para buscar cualquier modelo."
            else:
                raw_val = " ".join(args)
                if raw_val.lower().strip() == "reset":
                    models_list = []
                    reply_text = "cualquier modelo"
                else:
                    models_list = [m.strip().capitalize() for m in raw_val.split(",") if m.strip()]
                    reply_text = ", ".join(models_list)
                for s in config_data.get("searches", []):
                    if "vehicle" not in s:
                        s["vehicle"] = {}
                    s["vehicle"]["models"] = models_list
                modified = True
                reply = f"✅ ¡Modelos de búsqueda actualizados a: *{reply_text}*!"

        elif command in ["/kilometraje", "/km"]:
            if not args:
                reply = "⚠️ Especifica el kilometraje máximo. Ej: `/km 100000`"
            else:
                try:
                    val = int(args[0])
                    for s in config_data.get("searches", []):
                        if "vehicle" not in s:
                            s["vehicle"] = {}
                        s["vehicle"]["max_mileage_km"] = val
                    modified = True
                    reply = f"✅ ¡Kilometraje máximo actualizado a *{val:,} km*!"
                except ValueError:
                    reply = "⚠️ El kilometraje debe ser un número entero."

        elif command in ["/ano", "/year"]:
            if not args:
                reply = "⚠️ Especifica el año mínimo. Ej: `/ano 2012`"
            else:
                try:
                    val = int(args[0])
                    for s in config_data.get("searches", []):
                        if "vehicle" not in s:
                            s["vehicle"] = {}
                        s["vehicle"]["min_year"] = val
                    modified = True
                    reply = f"✅ ¡Año mínimo actualizado a *{val}*!"
                except ValueError:
                    reply = "⚠️ El año debe ser un número entero."
                    
        elif command == "/analizar":
            reply = "🚀 Iniciando monitorización y búsqueda de coches..."
            
        else:
            reply = "❓ Comando no reconocido. Usa `/help` para ver la lista de comandos."
            
        if reply:
            try:
                send_url = f"https://api.telegram.org/bot{token}/sendMessage"
                httpx.post(send_url, json={
                    "chat_id": chat_id,
                    "text": reply,
                    "parse_mode": "Markdown"
                }, timeout=10)
            except Exception as e:
                logger.error(f"Error sending command reply to Telegram: {e}")
                
    if modified:
        try:
            with open(searches_file, "w", encoding="utf-8") as f:
                yaml.safe_dump(config_data, f, default_flow_style=False, allow_unicode=True)
            logger.info("Search config updated via Telegram command.")
        except Exception as e:
            logger.error(f"Error writing searches.yaml: {e}")
            
    if new_last_update_id > last_update_id:
        try:
            session.execute(text("INSERT OR REPLACE INTO botstate (key, value) VALUES ('last_update_id', :val)"), {"val": str(new_last_update_id)})
            session.commit()
        except Exception as e:
            logger.error(f"Error saving last_update_id to database: {e}")
