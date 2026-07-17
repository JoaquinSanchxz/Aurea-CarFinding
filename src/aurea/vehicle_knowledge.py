from typing import List, Optional
from pydantic import BaseModel

class VehicleProfile(BaseModel):
    make: str
    model: str
    generation: Optional[str] = None
    engine: Optional[str] = None
    reliability_score: float  # 0 to 100
    parts_availability_score: float  # 0 to 100
    parts_cost_score: float  # 0 to 100 (high is cheaper/better)
    maintenance_score: float  # 0 to 100 (high is cheaper/better)
    efficiency_score: float  # 0 to 100
    performance_balance_score: float  # 0 to 100
    resale_score: float  # 0 to 100
    known_issues: List[str]
    expensive_service_points: List[int]  # Mileage values (e.g. 90000 for timing belt)
    confidence: float  # 0.0 to 1.0

# Predefined high-quality profiles
KNOWLEDGE_BASE = {
    ("toyota", "corolla"): VehicleProfile(
        make="Toyota",
        model="Corolla",
        reliability_score=95.0,
        parts_availability_score=92.0,
        parts_cost_score=85.0,
        maintenance_score=82.0,
        efficiency_score=90.0,
        performance_balance_score=80.0,
        resale_score=92.0,
        known_issues=["ruido de transmisión e-CVT bajo fuerte aceleración", "batería de 12V se descarga si no se usa"],
        expensive_service_points=[90000, 180000],  # Mantenimiento de refrigerante híbrido e inversor
        confidence=0.98
    ),
    ("volkswagen", "golf"): VehicleProfile(
        make="Volkswagen",
        model="Golf",
        reliability_score=82.0,
        parts_availability_score=95.0,
        parts_cost_score=78.0,
        maintenance_score=75.0,
        efficiency_score=80.0,
        performance_balance_score=85.0,
        resale_score=88.0,
        known_issues=["fugas en bomba de agua", "desgaste prematuro de embragues DSG en ciudad", "fallos de software de infoentretenimiento"],
        expensive_service_points=[60000, 120000],  # Mantenimiento de caja DSG / correa distribución
        confidence=0.95
    ),
    ("peugeot", "308"): VehicleProfile(
        make="Peugeot",
        model="308",
        reliability_score=40.0,  # Unreliable engine issues
        parts_availability_score=85.0,
        parts_cost_score=80.0,
        maintenance_score=70.0,
        efficiency_score=80.0,
        performance_balance_score=75.0,
        resale_score=60.0,
        known_issues=["degradación de la correa bañada en aceite (1.2 PureTech)", "alto consumo de aceite", "obstrucción del tamiz de aceite"],
        expensive_service_points=[60000, 100000],  # Cambio preventivo correa distribución
        confidence=0.92
    ),
    ("subaru", "wrx"): VehicleProfile(
        make="Subaru",
        model="WRX",
        reliability_score=72.0,
        parts_availability_score=60.0,
        parts_cost_score=55.0,
        maintenance_score=50.0,
        efficiency_score=55.0,
        performance_balance_score=90.0,
        resale_score=82.0,
        known_issues=["junta de culata propensa a fugas", "fallo de pistón ringland en conducción agresiva", "desgaste del diferencial"],
        expensive_service_points=[100000],
        confidence=0.89
    ),
    ("hyundai", "i30"): VehicleProfile(
        make="Hyundai",
        model="i30",
        reliability_score=86.0,
        parts_availability_score=90.0,
        parts_cost_score=88.0,
        maintenance_score=85.0,
        efficiency_score=82.0,
        performance_balance_score=80.0,
        resale_score=80.0,
        known_issues=["ruidos en la dirección asistida", "desgaste prematuro de embragues en DCT"],
        expensive_service_points=[90000],
        confidence=0.94
    )
}

def get_vehicle_profile(make: str, model: str) -> VehicleProfile:
    key = (make.lower().strip(), model.lower().strip())
    
    # Try finding exact match
    if key in KNOWLEDGE_BASE:
        return KNOWLEDGE_BASE[key]
        
    # Fallback to general make database or default low-confidence profile
    # Let's generate a default profile with low confidence so it gets rejected by Aurea requirements
    return VehicleProfile(
        make=make,
        model=model,
        reliability_score=50.0,
        parts_availability_score=50.0,
        parts_cost_score=50.0,
        maintenance_score=50.0,
        efficiency_score=50.0,
        performance_balance_score=50.0,
        resale_score=50.0,
        known_issues=["Información insuficiente sobre el modelo"],
        expensive_service_points=[],
        confidence=0.50  # Low confidence will block AUREA alerts (requires >= 0.88)
    )
