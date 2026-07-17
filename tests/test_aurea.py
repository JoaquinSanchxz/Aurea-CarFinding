import pytest
from datetime import datetime, timedelta
from sqlmodel import Session, SQLModel, create_engine, select

from aurea.models import Listing, Evaluation, PriceHistory, Notification, get_utc_now
from aurea.config import SearchConfig, VehicleFilter, PriceFilter, ExclusionsFilter
from aurea.normalizer import normalize_listing
from aurea.filters import pre_filter_listing, is_damaged, is_financed
from aurea.deduplication import are_listings_equivalent, process_duplicates_and_persist
from aurea.vehicle_knowledge import get_vehicle_profile
from aurea.market import analyze_market, MarketAnalysis
from aurea.risk import calculate_risk
from aurea.scoring import evaluate_listing, is_aurea_opportunity, calculate_adjusted_saving
from aurea.pipeline import double_validate_opportunity, run_pipeline, retry_failed_notifications
from aurea.sources.base import RawListing

@pytest.fixture(name="db_session")
def fixture_db_session():
    # In-memory SQLite for testing
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@pytest.fixture(name="search_config")
def fixture_search_config():
    return SearchConfig(
        id="test_search",
        enabled=True,
        vehicle=VehicleFilter(
            makes=[],
            models=[],
            min_year=2019,
            max_mileage_km=100000,
            fuels=["hybrid", "petrol"],
            transmissions=[]
        ),
        price=PriceFilter(
            max_price_eur=25000.0,
            minimum_adjusted_discount_percent=20.0,
            minimum_adjusted_saving_eur=3000.0
        ),
        exclusions=ExclusionsFilter(
            damaged=True,
            mechanical_failure=True,
            financing_price=True,
            no_itv=True,
            professional_only=True,
            auction=True,
            incomplete_documentation=True
        )
    )

def test_empty_makes_and_models(search_config):
    # Empty list means "accept all"
    # When makes/models are empty, we should not reject any valid brand/model.
    raw = RawListing(
        source_id="t1", source="wallapop", title="Mazda 3", description="Buen estado.",
        url="http://test.com", price=15000, make="Mazda", model="3", year=2020, mileage_km=40000,
        fuel="petrol", transmission="manual"
    )
    listing = normalize_listing(raw)
    keep, reason = pre_filter_listing(listing, search_config)
    assert keep is True
    assert reason == ""

def test_old_listing(search_config):
    raw = RawListing(
        source_id="t2", source="wallapop", title="Toyota Corolla", description="Buen estado.",
        url="http://test.com", price=18000, make="Toyota", model="Corolla", year=2020, mileage_km=50000,
        fuel="hybrid", transmission="automatic"
    )
    listing = normalize_listing(raw)
    listing.first_seen_at = get_utc_now() - timedelta(days=35)
    keep, reason = pre_filter_listing(listing, search_config)
    assert keep is False
    assert "Con más de 30 días" in reason

def test_financed_price(search_config):
    # Explicitly financed listing description
    raw = RawListing(
        source_id="t3", source="wallapop", title="Toyota Corolla",
        description="Precio de 15900€ sujeto a financiación mínima. Al contado 18900€.",
        url="http://test.com", price=15900, make="Toyota", model="Corolla", year=2021, mileage_km=40000,
        fuel="hybrid", transmission="automatic"
    )
    listing = normalize_listing(raw)
    assert is_financed(listing) is True
    keep, reason = pre_filter_listing(listing, search_config)
    assert keep is False
    assert "Precio financiado" in reason

def test_monthly_payment_as_price(search_config):
    # Suspiciously low price combined with 'mes' or 'cuota'
    raw = RawListing(
        source_id="t4", source="wallapop", title="Toyota Corolla",
        description="Llévatelo por solo 199 euros al mes sin entrada.",
        url="http://test.com", price=199, make="Toyota", model="Corolla", year=2021, mileage_km=40000,
        fuel="hybrid", transmission="automatic"
    )
    listing = normalize_listing(raw)
    assert is_financed(listing) is True
    keep, reason = pre_filter_listing(listing, search_config)
    assert keep is False
    assert "Precio financiado" in reason

def test_damage_and_negation_of_damage(search_config):
    # 1. Damaged listing
    raw_damaged = RawListing(
        source_id="t5", source="wallapop", title="Toyota Corolla con averia",
        description="Tiene junta culata rota para reparar, de ahí el precio.",
        url="http://test.com", price=12000, make="Toyota", model="Corolla", year=2020, mileage_km=80000,
        fuel="hybrid", transmission="automatic"
    )
    listing_damaged = normalize_listing(raw_damaged)
    assert is_damaged(listing_damaged) is True
    
    # 2. Negated damage (e.g. "no tiene averías")
    raw_clean = RawListing(
        source_id="t6", source="wallapop", title="Toyota Corolla impecable",
        description="Coche en perfecto estado, no tiene averias de ningun tipo. ITV recién pasada.",
        url="http://test.com", price=19000, make="Toyota", model="Corolla", year=2021, mileage_km=60000,
        fuel="hybrid", transmission="automatic"
    )
    listing_clean = normalize_listing(raw_clean)
    assert is_damaged(listing_clean) is False

def test_upcoming_expensive_service():
    profile = get_vehicle_profile("Toyota", "Corolla")
    # Exp service at 90k and 180k
    listing = Listing(
        source_id="t7", source="wallapop", title="Toyota Corolla", description="Normal description.",
        url="http://test.com", price=19000, make="Toyota", model="Corolla", year=2021, mileage_km=88000, # close to 90k
        fuel="hybrid", transmission="automatic"
    )
    # MarketExpected is 22000
    from aurea.market import MarketAnalysis
    market = MarketAnalysis(expected_price=22000.0)
    raw_sav, maint, rep, adj_sav = calculate_adjusted_saving(listing, market, profile)
    # Proximity to 90k (+/- 5000) should trigger a 500 EUR maintenance charge
    assert maint == 500.0

def test_scarce_parts_unknown_model(db_session, search_config):
    # Unknown/rare make/model defaults to low parts availability/low reliability
    raw = RawListing(
        source_id="t8", source="wallapop", title="Exotic Car 123",
        description="Coche raro.",
        url="http://test.com", price=15000, make="ExoticBrand", model="RareModel", year=2021, mileage_km=50000,
        fuel="petrol", transmission="manual"
    )
    listing = normalize_listing(raw)
    profile = get_vehicle_profile(listing.make, listing.model)
    assert profile.confidence == 0.50
    assert profile.reliability_score == 50.0

def test_unreliable_engine(db_session, search_config):
    # Peugeot 308 1.2 PureTech has reliability_score = 40.0
    profile = get_vehicle_profile("Peugeot", "308")
    assert profile.reliability_score == 40.0
    
    listing = Listing(
        id=1, source_id="t9", source="wallapop", title="Peugeot 308 1.2", description="Buen estado.",
        url="http://test.com", price=11000, make="Peugeot", model="308", year=2020, mileage_km=60000,
        fuel="petrol", transmission="manual"
    )
    market = MarketAnalysis(expected_price=14000.0)
    eval_data = evaluate_listing(listing, market, 5.0)
    
    # An unreliable engine should not qualify for AUREA opportunity (requires reliability >= 85)
    is_aurea = is_aurea_opportunity(listing, eval_data, search_config)
    assert is_aurea is False

def test_few_comparables(db_session, search_config):
    listing = Listing(
        id=1, source_id="t10", source="wallapop", title="Toyota Corolla", description="Buen estado.",
        url="http://test.com", price=18000, make="Toyota", model="Corolla", year=2021, mileage_km=50000,
        fuel="hybrid", transmission="automatic"
    )
    # If we only have 2 comparables in DB
    c1 = Listing(
        id=2, source_id="c1", source="coches_net", title="Toyota Corolla", description="Comp.",
        url="http://test.com/c1", price=22000, make="Toyota", model="Corolla", year=2021, mileage_km=48000,
        fuel="hybrid", transmission="automatic"
    )
    db_session.add(listing)
    db_session.add(c1)
    db_session.commit()
    
    market = analyze_market(db_session, listing)
    assert market.comparables_count < 5
    assert market.market_confidence == 0.0

def test_duplicates_between_portals(db_session):
    # Same car published on Wallapop and Milanuncios
    l1 = Listing(
        source_id="wp_abc", source="wallapop", title="Toyota Corolla 2021 Hybrid",
        description="Único dueño, muy mimado. Pasadas todas las revisiones en Toyota oficial.",
        url="http://wallapop.com/item/1", price=19000, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="hybrid", transmission="automatic"
    )
    l2 = Listing(
        source_id="ma_abc", source="milanuncios", title="Toyota Corolla Hybrid Active 122cv",
        description="Unico dueno, muy mimado. Pasadas todas las revisiones en casa oficial.",
        url="http://milanuncios.com/1", price=19000, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="hybrid", transmission="automatic"
    )
    assert are_listings_equivalent(l1, l2) is True

def test_republications_and_price_history(db_session):
    # Same source_id, price changes
    ext = Listing(
        id=1, source_id="wp_rep", source="wallapop", title="Toyota Corolla 2021",
        description="Excelente estado general.",
        url="http://wallapop.com/item/rep", price=21000, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="hybrid", transmission="automatic", is_active=True
    )
    db_session.add(ext)
    db_session.commit()
    
    # New listing detected (price dropped to 19000)
    new_listing = Listing(
        source_id="wp_rep", source="wallapop", title="Toyota Corolla 2021",
        description="Excelente estado general. Rebajado.",
        url="http://wallapop.com/item/rep", price=19000, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="hybrid", transmission="automatic", is_active=True
    )
    
    unique_list = process_duplicates_and_persist(db_session, [new_listing])
    # Should not insert a new listing, should return the existing updated listing
    assert len(unique_list) == 1  # Returned for re-evaluation
    
    # Fetch existing and check price is updated and price history contains old price
    db_session.expire_all()
    updated = db_session.get(Listing, 1)
    assert updated.price == 19000.0
    
    history_items = db_session.exec(select(PriceHistory).where(PriceHistory.listing_id == 1)).all()
    assert len(history_items) == 1
    assert history_items[0].price == 21000.0

def test_apparent_saving_vs_adjusted_saving():
    profile = get_vehicle_profile("Toyota", "Corolla")
    listing = Listing(
        source_id="t11", source="wallapop", title="Toyota Corolla con correa rota",
        description="Coche con correa de distribucion a cambiar muy pronto. Ademas neumaticos gastados.",
        url="http://test.com", price=18000, make="Toyota", model="Corolla", year=2021, mileage_km=89000,
        fuel="hybrid", transmission="automatic"
    )
    market = MarketAnalysis(expected_price=22000.0)
    
    # Apparent saving: 22000 - 18000 = 4000
    raw_sav, maint, rep, adj_sav = calculate_adjusted_saving(listing, market, profile)
    # maint near 90k: 500 + text check "correa de distribucion" 600 = 1100
    # rep base 150 + neumaticos 300 = 450
    # Total expenses: 1100 + 450 = 1550
    # Adjusted saving: 4000 - 1550 = 2450
    assert raw_sav == 4000.0
    assert adj_sav == 2450.0

def test_candidate_9_9_non_alerting(search_config):
    # Coche con descuento ajustado de 18% (menos de 20%) -> No se notifica
    listing = Listing(
        source_id="t12", source="wallapop", title="Toyota Corolla 2021",
        description="Excelente coche, muy cuidado.",
        url="http://test.com", price=19500, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="hybrid", transmission="automatic"
    )
    market = MarketAnalysis(
        expected_price=23000.0,
        comparables_count=10,
        market_confidence=0.92
    )
    eval_data = evaluate_listing(listing, market, 5.0)
    # Adjust discount to under 20%
    eval_data.discount_percent = 18.0
    is_aurea = is_aurea_opportunity(listing, eval_data, search_config)
    assert is_aurea is False

def test_opportunity_10_10(search_config):
    # Meets all requirements
    listing = Listing(
        id=1, source_id="t13", source="wallapop", title="Toyota Corolla 2021",
        description="Excelente estado, unico dueño, mantenimiento oficial.",
        url="http://test.com", price=18500, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="hybrid", transmission="automatic", is_active=True
    )
    market = MarketAnalysis(
        expected_price=23200.0,
        comparables_count=12,
        market_confidence=0.94
    )
    eval_data = evaluate_listing(listing, market, 8.0)
    # Ensure it meets specific numeric thresholds
    eval_data.discount_percent = 21.0
    eval_data.adjusted_saving_eur = 3500.0
    eval_data.score_global = 96.0
    
    is_aurea = is_aurea_opportunity(listing, eval_data, search_config)
    assert is_aurea is True

def test_double_validation_failure(db_session, search_config):
    # Potential Aurea, but double validation fails because listing is inactive
    listing = Listing(
        id=1, source_id="t14", source="wallapop", title="Toyota Corolla",
        description="Buen coche.",
        url="http://test.com", price=18000, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="hybrid", transmission="automatic", is_active=False # INACTIVE!
    )
    market = MarketAnalysis(expected_price=23000.0, comparables_count=10, market_confidence=0.92)
    eval_data = evaluate_listing(listing, market, 5.0)
    
    passed = double_validate_opportunity(db_session, listing, eval_data, search_config)
    assert passed is False

def test_telegram_down_without_losing_opportunity(db_session):
    # Test that failed notification preserves Aurea classification but stores "failed" status
    listing = Listing(
        id=101, source_id="t15", source="wallapop", title="Toyota Corolla",
        description="Buen coche.",
        url="http://test.com", price=18000, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="hybrid", transmission="automatic", is_aurea=True, opportunity_id="AU-000101"
    )
    db_session.add(listing)
    db_session.commit()
    
    # Store a failed notification
    notif = Notification(
        listing_id=listing.id,
        opportunity_id=listing.opportunity_id,
        status="failed",
        error_message="Telegram API down"
    )
    db_session.add(notif)
    db_session.commit()
    
    # Check that failed notification is still in DB
    saved = db_session.exec(select(Notification).where(Notification.status == "failed")).first()
    assert saved is not None
    assert saved.opportunity_id == "AU-000101"

def test_location_places_filter(search_config):
    search_config.location.places = ["cordoba", "malaga"]
    
    # 1. Matching location Málaga
    l1 = Listing(
        source_id="loc_1", source="wallapop", title="Car", description="Desc",
        url="http://test.com", price=12000, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="hybrid", transmission="automatic", location="Málaga, España"
    )
    keep, _ = pre_filter_listing(l1, search_config)
    assert keep is True
    
    # 2. Matching location Córdoba
    l2 = Listing(
        source_id="loc_2", source="wallapop", title="Car", description="Desc",
        url="http://test.com", price=12000, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="hybrid", transmission="automatic", location="Córdoba, ES"
    )
    keep, _ = pre_filter_listing(l2, search_config)
    assert keep is True
    
    # 3. Non-matching location Madrid
    l3 = Listing(
        source_id="loc_3", source="wallapop", title="Car", description="Desc",
        url="http://test.com", price=12000, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="hybrid", transmission="automatic", location="Madrid, ES"
    )
    keep, _ = pre_filter_listing(l3, search_config)
    assert keep is False

def test_preferred_fuel_bonus_and_ignore_discount(search_config):
    # Disable discount thresholds
    search_config.price.minimum_adjusted_discount_percent = 0.0
    search_config.price.minimum_adjusted_saving_eur = 0.0
    
    # Prefer diesel fuel
    search_config.vehicle.preferred_fuels = ["diesel"]
    
    listing = Listing(
        source_id="fuel_1", source="wallapop", title="Car", description="Desc",
        url="http://test.com", price=12000, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="diesel", transmission="automatic", location="Málaga, España"
    )
    market = MarketAnalysis(expected_price=12000.0, comparables_count=10, market_confidence=0.95)
    
    # Check that discount_score defaults to 100 because discount threshold is 0.0,
    # and fuel preference boosts the score
    eval_data = evaluate_listing(listing, market, 0.0, search=search_config)
    assert eval_data.score_global >= 95.0
    
    # Since minimum thresholds are 0.0, it qualifies as Aurea even without discount
    is_aurea = is_aurea_opportunity(listing, eval_data, search_config)
    assert is_aurea is True

def test_dynamic_rating_threshold(search_config):
    # Setup search config to require 10 rating and disable discount thresholds
    search_config.alerting.required_rating = 10
    search_config.price.minimum_adjusted_discount_percent = 0.0
    search_config.price.minimum_adjusted_saving_eur = 0.0
    
    # Create evaluation data with a score_global of 91.0 (fails 10/10 which needs 95.0)
    # but satisfies all other relaxed thresholds
    listing = Listing(
        source_id="rate_9", source="wallapop", title="Car", description="Desc",
        url="http://test.com", price=12000, make="Toyota", model="Corolla", year=2021, mileage_km=70000,
        fuel="diesel", transmission="automatic", location="Málaga, España"
    )
    market = MarketAnalysis(expected_price=12000.0, comparables_count=10, market_confidence=0.95)
    eval_data = evaluate_listing(listing, market, 0.0, search=search_config)
    
    # Manually tweak global score to be 91.0 (between 90.0 and 95.0)
    eval_data.score_global = 91.0
    
    # Under required_rating = 10, this should be False
    assert is_aurea_opportunity(listing, eval_data, search_config) is False
    
    # Tweak config to allow 9 rating
    search_config.alerting.required_rating = 9
    
    # Under required_rating = 9, this should be True
    assert is_aurea_opportunity(listing, eval_data, search_config) is True

def test_geocoding_cache(db_session):
    from aurea.filters import get_distance_km
    from aurea.models import LocationCoordinate
    
    # Baena is not in CITIES_COORDINATES, so it must query Nominatim and cache it
    dist = get_distance_km("Rute", "Baena, ES", session=db_session)
    assert dist is not None
    assert 30.0 < dist < 45.0  # Baena is around 36 km from Rute
    
    # Check cache table has Baena
    db_session.expire_all()
    cached = db_session.get(LocationCoordinate, "baena")
    assert cached is not None
    assert 37.0 < cached.latitude < 38.0
    assert -4.5 < cached.longitude < -4.0
    
    # Request without session should return None because it is not in predefined dict
    dist_no_session = get_distance_km("Rute", "Baena, ES", session=None)
    assert dist_no_session is None

