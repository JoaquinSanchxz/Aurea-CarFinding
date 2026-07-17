import sys
from datetime import datetime
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.status import Status
from rich import print as rprint
from sqlmodel import select, Session, func

from aurea.pipeline import run_pipeline, retry_failed_notifications
from aurea.database import get_session, init_db
from aurea.models import Listing, Evaluation, Notification
from aurea.config import load_settings, load_searches
from aurea.telegram import send_test_message

app = typer.Typer(help="Aurea: Monitoreo de coches y alertas premium en Telegram.")
console = Console()

@app.command()
def run():
    """
    Ejecuta el ciclo de monitorización, recopilando y analizando nuevos anuncios.
    """
    init_db()
    with console.status("[bold green]Buscando oportunidades en Wallapop, Milanuncios y Coches.net...") as status:
        # First retry any previously failed telegram alerts
        retry_failed_notifications()
        
        # Execute pipeline
        summary = run_pipeline()
        
    # Output matching the requested format exactly:
    rprint(f"\n[bold white]Anuncios encontrados:[/bold white] [cyan]{summary['encontrados']}[/cyan]")
    rprint(f"[bold white]Nuevos:[/bold white] [green]{summary['nuevos']}[/green]")
    rprint(f"[bold white]Descartados:[/bold white] [yellow]{summary['descartados']}[/yellow]")
    rprint(f"[bold white]Analizados:[/bold white] [blue]{summary['analizados']}[/blue]")
    rprint(f"[bold white]Candidatos:[/bold white] [magenta]{summary['candidatos']}[/magenta]")
    rprint(f"[bold white]Aurea:[/bold white] [red]{summary['aurea']}[/red]")
    rprint(f"[bold white]Alertas enviadas:[/bold white] [bold green]{summary['alertas_enviadas']}[/bold green]\n")

@app.command()
def history(
    source: Optional[str] = typer.Option(None, help="Filtrar por portal de origen (wallapop, milanuncios, coches_net)"),
    make: Optional[str] = typer.Option(None, help="Filtrar por marca del vehículo")
):
    """
    Muestra el histórico de oportunidades detectadas.
    """
    init_db()
    session = get_session()
    
    stmt = select(Listing).where(Listing.is_aurea == True)
    if source:
        stmt = stmt.where(Listing.source == source.lower().strip())
    if make:
        stmt = stmt.where(Listing.make == make.capitalize().strip())
        
    listings = session.exec(stmt).all()
    session.close()
    
    if not listings:
        rprint("[bold yellow]No se encontraron oportunidades en el histórico que coincidan con los filtros.[/bold yellow]")
        return

    table = Table(title="Histórico de Oportunidades Aurea", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=12)
    table.add_column("Vehículo", style="bold white")
    table.add_column("Precio", style="green")
    table.add_column("Año", style="cyan")
    table.add_column("Km", style="yellow")
    table.add_column("Portal", style="blue")
    table.add_column("Enlace", style="dim")

    for l in listings:
        opp_id = l.opportunity_id or f"AU-{l.id:06d}"
        table.add_row(
            opp_id,
            f"{l.make} {l.model}",
            f"{l.price:,.0f} €",
            str(l.year),
            f"{l.mileage_km:,}",
            l.source.capitalize(),
            l.url
        )
        
    console.print(table)

@app.command()
def show(opportunity_id: str):
    """
    Muestra los detalles completos y análisis de una oportunidad específica.
    """
    init_db()
    session = get_session()
    
    stmt = select(Listing).where(Listing.opportunity_id == opportunity_id)
    listing = session.exec(stmt).first()
    
    if not listing:
        # Try matching by database ID format, e.g. if we input just AU-000001
        stmt = select(Listing).where(Listing.id == int(opportunity_id.split("-")[-1]))
        listing = session.exec(stmt).first()
        
    if not listing:
        rprint(f"[bold red]Error: No se encontró ninguna oportunidad con el identificador {opportunity_id}[/bold red]")
        session.close()
        raise typer.Exit(code=1)
        
    # Get latest evaluation
    eval_stmt = select(Evaluation).where(Evaluation.listing_id == listing.id).order_by(Evaluation.evaluated_at.desc())
    eval_data = session.exec(eval_stmt).first()
    session.close()
    
    if not eval_data:
        rprint(f"[bold yellow]Advertencia: Coche encontrado pero no tiene análisis completo guardado.[/bold yellow]")
        return
        
    details = f"""
[bold cyan]Vehículo:[/bold cyan] {listing.make} {listing.model}
[bold cyan]Año/Combustible/Caja:[/bold cyan] {listing.year} · {listing.fuel.upper()} · {listing.transmission.upper()}
[bold cyan]Kilometraje:[/bold cyan] {listing.mileage_km:,} km
[bold cyan]Ubicación:[/bold cyan] {listing.location}
[bold green]Precio Anunciado:[/bold green] {listing.price:,.0f} €
[bold green]Valor Estimado de Mercado:[/bold green] {eval_data.saving_eur + listing.price:,.0f} €
[bold green]Ahorro Ajustado:[/bold green] {eval_data.adjusted_saving_eur:,.0f} € ({eval_data.discount_percent}%)
[bold yellow]Comparables:[/bold yellow] {eval_data.num_comparables} (Confianza: {int(eval_data.market_confidence*100)}%)
[bold red]Riesgo Calculado:[/bold red] {eval_data.risk_score}/100

[bold white]Destaca por:[/bold white]
{chr(10).join(f' - {r.strip()}' for r in eval_data.reasons.split(',') if r.strip())}

[bold white]Puntos a Revisar:[/bold white]
{chr(10).join(f' - {w.strip()}' for w in eval_data.warnings.split(',') if w.strip())}

[bold blue]Portal de Origen:[/bold blue] {listing.source.capitalize()}
[bold blue]Enlace Original:[/bold blue] {listing.url}
"""
    panel = Panel(details, title=f"Ficha Detallada: {opportunity_id}", expand=False, border_style="bold green")
    console.print(panel)

@app.command()
def stats():
    """
    Muestra estadísticas globales del sistema de monitorización.
    """
    init_db()
    session = get_session()
    
    total_listings = session.exec(select(func.count(Listing.id))).one()
    total_aurea = session.exec(select(func.count(Listing.id)).where(Listing.is_aurea == True)).one()
    total_alerts_sent = session.exec(select(func.count(Notification.id)).where(Notification.status == "sent")).one()
    total_alerts_failed = session.exec(select(func.count(Notification.id)).where(Notification.status == "failed")).one()
    
    # Calculate price changes count
    from aurea.models import PriceHistory
    total_price_updates = session.exec(select(func.count(PriceHistory.id))).one()
    
    session.close()
    
    details = f"""
[bold white]Total anuncios recopilados:[/bold white] [cyan]{total_listings}[/cyan]
[bold white]Actualizaciones de precio registradas:[/bold white] [cyan]{total_price_updates}[/cyan]
[bold white]Oportunidades Aurea (10/10) catalogadas:[/bold white] [green]{total_aurea}[/green]
[bold white]Alertas enviadas con éxito:[/bold white] [green]{total_alerts_sent}[/green]
[bold white]Alertas fallidas/pendientes de reintento:[/bold white] [red]{total_alerts_failed}[/red]
"""
    panel = Panel(details, title="Estadísticas de Aurea", expand=False, border_style="cyan")
    console.print(panel)

@app.command()
def doctor():
    """
    Verifica el estado del sistema, archivos de configuración, base de datos y conexión a Telegram.
    """
    rprint("[bold white]Iniciando diagnóstico del sistema Aurea...[/bold white]\n")
    
    # 1. Config directories and files
    settings = load_settings()
    searches = load_searches()
    
    rprint(f"[*] Archivo settings.yaml: [green]Cargado correctamente[/green]")
    rprint(f"[*] Archivo searches.yaml: [green]Cargado correctamente ({len(searches)} búsquedas configuradas)[/green]")
    
    # 2. Database check
    try:
        init_db()
        session = get_session()
        # Query count to verify connection
        session.exec(select(func.count(Listing.id))).one()
        session.close()
        rprint("[*] Base de datos SQLite: [green]Conexión correcta y tablas inicializadas[/green]")
    except Exception as e:
        rprint(f"[*] Base de datos SQLite: [bold red]ERROR - {e}[/bold red]")
        
    # 3. Telegram verification
    bot_token = settings.telegram.bot_token
    chat_id = settings.telegram.chat_id
    
    if bot_token and chat_id:
        rprint(f"[*] Configuración Telegram: [green]Configurada (Token: {bot_token[:6]}... / Chat ID: {chat_id})[/green]")
        # Test connection
        with console.status("[bold green]Verificando conexión con Telegram Bot API...") as status:
            success = send_test_message()
        if success:
            rprint("[*] Conexión Telegram API: [green]ÉXITO - Mensaje de prueba recibido[/green]")
        else:
            rprint("[*] Conexión Telegram API: [bold red]FALLIDA - Comprueba el token, el chat_id o el acceso a internet[/bold red]")
    else:
        rprint("[*] Configuración Telegram: [bold yellow]INCOMPLETA - Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID[/bold yellow]")

@app.command()
def test_telegram():
    """
    Envía un mensaje de prueba al chat de Telegram configurado.
    """
    rprint("[bold cyan]Enviando mensaje de prueba a Telegram...[/bold cyan]")
    success = send_test_message()
    if success:
        rprint("[bold green]¡Mensaje enviado con éxito! Comprueba tu Telegram.[/bold green]")
    else:
        rprint("[bold red]Error al enviar mensaje. Revisa tu archivo .env o settings.yaml.[/bold red]")

if __name__ == "__main__":
    app()
