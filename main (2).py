#!/usr/bin/env python3
"""
FGCU Traffic API - FastAPI Backend
Provides real-time traffic data and AI forecasting endpoints
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import random
import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel
import logging
import os
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import routers
try:
    from cesium_integration import cesium_router
    logger.info("✅ Cesium integration module loaded")
except ImportError as e:
    logger.warning(f"⚠️ Cesium integration module not available: {e}")
    cesium_router = None

try:
    from websocket_streaming import websocket_router
    logger.info("✅ WebSocket streaming module loaded")
except ImportError as e:
    logger.warning(f"⚠️ WebSocket streaming module not available: {e}")
    websocket_router = None

try:
    from pavement_condition import pavement_router
    logger.info("✅ Pavement condition module loaded")
except ImportError as e:
    logger.warning(f"⚠️ Pavement condition module not available: {e}")
    pavement_router = None

# Import ADT client
try:
    from adt_client import ADTClient
    logger.info("✅ Azure Digital Twins client loaded")
    adt_client = None  # Will be initialized in lifespan
    ADTClient_available = True
except ImportError as e:
    logger.warning(f"⚠️ ADT client not available: {e}")
    adt_client = None
    ADTClient = None
    ADTClient_available = False

# Data models
class TrafficSegment(BaseModel):
    id: str
    name: str
    coordinates: List[List[float]]  # [[lon, lat], [lon, lat], ...]
    traffic_level: str  # HEAVY, MODERATE, LIGHT, MINIMAL, LOW
    volume: int  # vehicles per hour
    speed: float  # average speed in mph
    last_updated: str

class TrafficForecast(BaseModel):
    segment_id: str
    predictions: List[Dict[str, float]]  # [{"hour": 1, "volume": 250, "confidence": 0.85}, ...]
    generated_at: str
    model_accuracy: float

class SystemStatus(BaseModel):
    status: str
    active_segments: int
    last_update: str
    uptime: str
    ai_model_status: str

# Global state
traffic_data: Dict[str, TrafficSegment] = {}
system_start_time = datetime.datetime.now()

# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    global adt_client
    
    logger.info("🚀 Starting FGCU Traffic API...")
    
    # Initialize ADT client
    if ADTClient_available and ADTClient:
        try:
            adt_url = os.getenv("ADT_INSTANCE_URL", "https://fgcu-traffic-dt.api.eus.digitaltwins.azure.net")
            adt_client = ADTClient(adt_url)
            logger.info("✅ Azure Digital Twins client initialized")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize ADT client: {e}")
            adt_client = None
    
    # Initialize traffic data
    await initialize_traffic_data()
    
    # Start background tasks
    asyncio.create_task(update_traffic_loop())
    
    logger.info("✅ FGCU Traffic API is ready!")
    yield
    
    # Cleanup
    logger.info("🛑 Shutting down FGCU Traffic API...")

# Create FastAPI app
app = FastAPI(
    title="FGCU Traffic Management API",
    description="Real-time traffic monitoring and AI-powered forecasting for FGCU campus",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
if cesium_router:
    app.include_router(cesium_router)
    logger.info("✅ Cesium router included")

if websocket_router:
    app.include_router(websocket_router)
    logger.info("✅ WebSocket router included")

if pavement_router:
    app.include_router(pavement_router, prefix="/api")
    logger.info("✅ Pavement condition router included")

# FGCU road network configuration
FGCU_ROADS = [
    {
        "id": "bh_griffin_pkwy",
        "name": "Ben Hill Griffin Parkway",
        "coordinates": [
            [-81.795, 26.463], [-81.788, 26.462], [-81.781, 26.461], 
            [-81.774, 26.460], [-81.767, 26.459]
        ]
    },
    {
        "id": "fgcu_blvd",
        "name": "FGCU Boulevard",
        "coordinates": [
            [-81.773, 26.470], [-81.773, 26.465], [-81.773, 26.460], [-81.773, 26.455]
        ]
    },
    {
        "id": "campus_loop",
        "name": "Campus Loop Road",
        "coordinates": [
            [-81.776, 26.464], [-81.774, 26.466], [-81.772, 26.464], [-81.774, 26.462], [-81.776, 26.464]
        ]
    },
    {
        "id": "parking_access",
        "name": "Parking Access Road",
        "coordinates": [
            [-81.775, 26.463], [-81.773, 26.463], [-81.771, 26.463]
        ]
    },
    {
        "id": "library_dr",
        "name": "Library Drive",
        "coordinates": [
            [-81.774, 26.465], [-81.772, 26.465], [-81.770, 26.465]
        ]
    }
]

async def initialize_traffic_data():
    """Initialize traffic data for all road segments"""
    global traffic_data
    
    traffic_levels = ['HEAVY', 'MODERATE', 'LIGHT', 'MINIMAL', 'LOW']
    
    for road in FGCU_ROADS:
        level = random.choice(traffic_levels)
        volume = generate_traffic_volume(level)
        speed = generate_speed(level)
        
        traffic_data[road["id"]] = TrafficSegment(
            id=road["id"],
            name=road["name"],
            coordinates=road["coordinates"],
            traffic_level=level,
            volume=volume,
            speed=speed,
            last_updated=datetime.datetime.now().isoformat()
        )
    
    logger.info(f"Initialized {len(traffic_data)} traffic segments")

def generate_traffic_volume(level: str) -> int:
    """Generate realistic traffic volume based on level"""
    base_volumes = {
        'HEAVY': (400, 700),
        'MODERATE': (250, 400),
        'LIGHT': (150, 250),
        'MINIMAL': (75, 150),
        'LOW': (25, 75)
    }
    
    min_vol, max_vol = base_volumes.get(level, (100, 300))
    return random.randint(min_vol, max_vol)

def generate_speed(level: str) -> float:
    """Generate realistic speed based on traffic level"""
    base_speeds = {
        'HEAVY': (10, 25),
        'MODERATE': (25, 35),
        'LIGHT': (35, 45),
        'MINIMAL': (40, 50),
        'LOW': (45, 55)
    }
    
    min_speed, max_speed = base_speeds.get(level, (20, 40))
    return round(random.uniform(min_speed, max_speed), 1)

async def update_traffic_loop():
    """Background task to update traffic data periodically"""
    while True:
        try:
            await asyncio.sleep(30)  # Update every 30 seconds
            await update_traffic_data()
        except Exception as e:
            logger.error(f"Error in traffic update loop: {e}")

async def update_traffic_data():
    """Update traffic data with new random values"""
    global traffic_data
    
    traffic_levels = ['HEAVY', 'MODERATE', 'LIGHT', 'MINIMAL', 'LOW']
    
    for segment_id in traffic_data:
        # 70% chance to keep same level, 30% to change
        if random.random() < 0.7:
            current_level = traffic_data[segment_id].traffic_level
        else:
            current_level = random.choice(traffic_levels)
        
        volume = generate_traffic_volume(current_level)
        speed = generate_speed(current_level)
        
        traffic_data[segment_id].traffic_level = current_level
        traffic_data[segment_id].volume = volume
        traffic_data[segment_id].speed = speed
        traffic_data[segment_id].last_updated = datetime.datetime.now().isoformat()
    
    logger.info("Updated traffic data for all segments")

# API Endpoints

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "FGCU Traffic Management API",
        "version": "1.0.0",
        "status": "active",
        "endpoints": {
            "traffic": "/api/traffic",
            "status": "/api/status", 
            "forecast": "/api/forecast/{segment_id}",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.datetime.now().isoformat()}

@app.post("/api/pavement-condition-direct")
async def pavement_condition_direct(request: dict):
    """Direct pavement condition endpoint for testing"""
    try:
        from pavement_condition import pavement_model
        result = pavement_model.predict(
            latitude=request.get('latitude', 0),
            longitude=request.get('longitude', 0),
            heading=request.get('heading'),
            pitch=request.get('pitch')
        )
        return result
    except Exception as e:
        logger.error(f"Error in pavement condition: {e}")
        return {"error": str(e), "status": "failed"}

@app.get("/api/status", response_model=SystemStatus)
async def get_system_status():
    """Get system status and statistics"""
    uptime = datetime.datetime.now() - system_start_time
    uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds%3600)//60}m"
    
    return SystemStatus(
        status="active",
        active_segments=len(traffic_data),
        last_update=max([s.last_updated for s in traffic_data.values()]) if traffic_data else "N/A",
        uptime=uptime_str,
        ai_model_status="ready"
    )

@app.get("/api/traffic")
async def get_traffic_data():
    """Get current traffic data for all segments"""
    if not traffic_data:
        raise HTTPException(status_code=503, detail="Traffic data not available")
    
    return {
        "segments": list(traffic_data.values()),
        "total_segments": len(traffic_data),
        "last_updated": datetime.datetime.now().isoformat()
    }

@app.get("/api/traffic/{segment_id}")
async def get_segment_traffic(segment_id: str):
    """Get traffic data for a specific segment"""
    if segment_id not in traffic_data:
        raise HTTPException(status_code=404, detail=f"Segment {segment_id} not found")
    
    return traffic_data[segment_id]

@app.get("/api/forecast/{segment_id}", response_model=TrafficForecast)
async def get_traffic_forecast(segment_id: str, hours: int = 24):
    """Get AI-powered traffic forecast for a segment"""
    if segment_id not in traffic_data:
        raise HTTPException(status_code=404, detail=f"Segment {segment_id} not found")
    
    if hours < 1 or hours > 72:
        raise HTTPException(status_code=400, detail="Hours must be between 1 and 72")
    
    # Generate forecast predictions (simulated AI model)
    current_segment = traffic_data[segment_id]
    base_volume = current_segment.volume
    
    predictions = []
    for hour in range(1, hours + 1):
        # Simulate time-of-day patterns
        time_factor = 1.0
        if 6 <= hour % 24 <= 9:  # Morning rush
            time_factor = 1.5
        elif 16 <= hour % 24 <= 19:  # Evening rush
            time_factor = 1.4
        elif 22 <= hour % 24 or hour % 24 <= 5:  # Night
            time_factor = 0.3
        
        # Add some randomness
        random_factor = random.uniform(0.8, 1.2)
        predicted_volume = int(base_volume * time_factor * random_factor)
        
        # Ensure reasonable bounds
        predicted_volume = max(10, min(800, predicted_volume))
        
        predictions.append({
            "hour": hour,
            "volume": predicted_volume,
            "confidence": round(random.uniform(0.75, 0.95), 2)
        })
    
    return TrafficForecast(
        segment_id=segment_id,
        predictions=predictions,
        generated_at=datetime.datetime.now().isoformat(),
        model_accuracy=0.89
    )

@app.post("/api/traffic/update")
async def manual_traffic_update(background_tasks: BackgroundTasks):
    """Manually trigger traffic data update"""
    background_tasks.add_task(update_traffic_data)
    return {"message": "Traffic update initiated", "timestamp": datetime.datetime.now().isoformat()}

@app.get("/api/segments")
async def get_available_segments():
    """Get list of all available traffic segments"""
    segments = [
        {"id": segment_id, "name": segment.name}
        for segment_id, segment in traffic_data.items()
    ]
    
    return {
        "segments": segments,
        "total": len(segments)
    }

# ========================================
# Azure Digital Twins Endpoints
# ========================================

@app.get("/api/adt/health")
async def adt_health_check():
    """Check Azure Digital Twins connection status"""
    if not adt_client:
        return {"status": "unavailable", "message": "ADT client not initialized"}
    
    return {
        "status": "connected",
        "adt_url": adt_client.adt_url,
        "timestamp": datetime.datetime.now().isoformat()
    }

@app.get("/api/adt/roads")
async def get_adt_roads(traffic_level: Optional[str] = None):
    """
    Get all road twins from Azure Digital Twins
    Query parameters:
    - traffic_level: Filter by traffic level (HEAVY, MODERATE, LIGHT, LOW)
    """
    if not adt_client:
        raise HTTPException(status_code=503, detail="ADT client not available")
    
    try:
        if traffic_level:
            roads = await adt_client.query_roads_by_traffic_level(traffic_level)
        else:
            # Query all roads
            query = "SELECT * FROM DIGITALTWINS WHERE IS_OF_MODEL('dtmi:fgcu:Road;1')"
            roads = await adt_client.query_twins(query)
        
        return {
            "roads": roads,
            "count": len(roads),
            "query": f"traffic_level={traffic_level}" if traffic_level else "all",
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error querying roads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/adt/roads/{road_id}")
async def get_adt_road(road_id: str):
    """Get specific road twin by ID"""
    if not adt_client:
        raise HTTPException(status_code=503, detail="ADT client not available")
    
    try:
        road = await adt_client.get_twin(road_id)
        if not road:
            raise HTTPException(status_code=404, detail=f"Road {road_id} not found")
        
        return road
    except Exception as e:
        logger.error(f"Error getting road {road_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/adt/roads/{road_id}/sensors")
async def get_road_sensors(road_id: str):
    """Get all sensors associated with a specific road"""
    if not adt_client:
        raise HTTPException(status_code=503, detail="ADT client not available")
    
    try:
        result = await adt_client.query_road_with_sensors(road_id)
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Road {road_id} not found")
        
        return {
            "road_id": road_id,
            "road": result.get("road"),
            "sensors": result.get("sensors", []),
            "sensor_count": len(result.get("sensors", [])),
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting sensors for road {road_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/adt/pavement")
async def get_adt_pavement(
    min_pci: Optional[int] = None,
    max_pci: Optional[int] = None,
    condition: Optional[str] = None
):
    """
    Get pavement asset twins from Azure Digital Twins
    Query parameters:
    - min_pci: Minimum PCI value (0-100)
    - max_pci: Maximum PCI value (0-100)
    - condition: Filter by condition (excellent/good/fair/poor/failed)
    """
    if not adt_client:
        raise HTTPException(status_code=503, detail="ADT client not available")
    
    try:
        if condition:
            pavements = await adt_client.query_pavement_by_condition(condition)
        elif min_pci is not None or max_pci is not None:
            min_val = min_pci if min_pci is not None else 0
            max_val = max_pci if max_pci is not None else 100
            pavements = await adt_client.query_pavement_by_pci_range(min_val, max_val)
        else:
            # Query all pavement assets
            query = "SELECT * FROM DIGITALTWINS WHERE IS_OF_MODEL('dtmi:fgcu:PavementAsset;1')"
            pavements = await adt_client.query_twins(query)
        
        return {
            "pavement_assets": pavements,
            "count": len(pavements),
            "filters": {
                "min_pci": min_pci,
                "max_pci": max_pci,
                "condition": condition
            },
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error querying pavement: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/adt/congestion")
async def get_congested_roads(min_speed: Optional[float] = 20.0):
    """
    Get roads with congestion (low average speed)
    Query parameters:
    - min_speed: Maximum average speed to consider congested (default: 20 mph)
    """
    if not adt_client:
        raise HTTPException(status_code=503, detail="ADT client not available")
    
    try:
        congested_roads = await adt_client.query_congested_roads(max_speed=min_speed)
        
        return {
            "congested_roads": congested_roads,
            "count": len(congested_roads),
            "threshold_speed": min_speed,
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error querying congested roads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/adt/roads/{road_id}/traffic")
async def update_road_traffic(road_id: str, traffic_data: dict):
    """
    Update traffic metrics for a specific road twin
    Request body:
    {
        "trafficLevel": "MODERATE",
        "averageSpeed": 35.0,
        "vehicleCount": 150
    }
    """
    if not adt_client:
        raise HTTPException(status_code=503, detail="ADT client not available")
    
    try:
        await adt_client.update_traffic_metrics(road_id, traffic_data)
        
        return {
            "message": "Traffic metrics updated",
            "road_id": road_id,
            "updated_data": traffic_data,
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error updating traffic for {road_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/adt/pavement/{pavement_id}/condition")
async def update_pavement_condition(pavement_id: str, condition_data: dict):
    """
    Update pavement condition for a specific pavement asset
    Request body:
    {
        "pci": 75,
        "iri": 2.5
    }
    """
    if not adt_client:
        raise HTTPException(status_code=503, detail="ADT client not available")
    
    try:
        pci = condition_data.get("pci")
        iri = condition_data.get("iri")
        
        if pci is None or iri is None:
            raise HTTPException(status_code=400, detail="Both 'pci' and 'iri' are required")
        
        await adt_client.update_pavement_condition(pavement_id, pci, iri)
        
        return {
            "message": "Pavement condition updated",
            "pavement_id": pavement_id,
            "pci": pci,
            "iri": iri,
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error updating pavement {pavement_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/adt/statistics")
async def get_adt_statistics():
    """Get overall statistics from Azure Digital Twins"""
    if not adt_client:
        raise HTTPException(status_code=503, detail="ADT client not available")
    
    try:
        # Query counts for different twin types
        road_query = "SELECT COUNT() FROM DIGITALTWINS WHERE IS_OF_MODEL('dtmi:fgcu:Road;1')"
        sensor_query = "SELECT COUNT() FROM DIGITALTWINS WHERE IS_OF_MODEL('dtmi:fgcu:TrafficSensor;1')"
        pavement_query = "SELECT COUNT() FROM DIGITALTWINS WHERE IS_OF_MODEL('dtmi:fgcu:PavementAsset;1')"
        
        # Execute queries (simplified - actual implementation would parse results)
        return {
            "statistics": {
                "total_roads": "Query ADT for count",
                "total_sensors": "Query ADT for count",
                "total_pavement_assets": "Query ADT for count",
                "last_updated": datetime.datetime.now().isoformat()
            },
            "message": "Full implementation requires ADT query result parsing"
        }
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Endpoint not found", "path": str(request.url.path)}
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "message": "Please check logs"}
    )

if __name__ == "__main__":
    import uvicorn
    
    # Development server
    logger.info("Starting development server...")
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )