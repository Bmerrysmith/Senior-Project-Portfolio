# WebSocket Streaming for Real-time Traffic Data

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime
import random

# Configure logging
logger = logging.getLogger(__name__)

# Create router
websocket_router = APIRouter(tags=["websocket"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Failed to broadcast to connection: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

# Global connection manager
manager = ConnectionManager()

@websocket_router.websocket("/ws/traffic")
async def websocket_traffic_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time traffic updates"""
    await manager.connect(websocket)
    try:
        # Start background task to send traffic updates
        asyncio.create_task(send_traffic_updates(websocket))
        
        while True:
            # Listen for client messages
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message.get("type") == "subscribe":
                road_id = message.get("road_id")
                logger.info(f"Client subscribed to road: {road_id}")
                
                # Send acknowledgment
                await manager.send_personal_message(
                    json.dumps({
                        "type": "subscription_confirmed",
                        "road_id": road_id,
                        "timestamp": datetime.now().isoformat()
                    }),
                    websocket
                )
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected from traffic WebSocket")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

async def send_traffic_updates(websocket: WebSocket):
    """Send periodic traffic updates to connected client"""
    try:
        while websocket in manager.active_connections:
            # Generate synthetic traffic data
            traffic_data = {
                "type": "traffic_update",
                "timestamp": datetime.now().isoformat(),
                "roads": [
                    {
                        "road_id": f"road_{i}",
                        "traffic_level": random.choice(["low", "moderate", "high"]),
                        "vehicle_count": random.randint(5, 50),
                        "average_speed": random.randint(15, 45),
                        "congestion_score": random.uniform(0.1, 0.9)
                    }
                    for i in range(1, 6)  # 5 roads
                ],
                "signals": [
                    {
                        "signal_id": f"signal_{i}",
                        "status": random.choice(["red", "yellow", "green"]),
                        "time_remaining": random.randint(10, 60),
                        "queue_length": random.randint(0, 15)
                    }
                    for i in range(1, 4)  # 3 signals
                ]
            }
            
            await manager.send_personal_message(
                json.dumps(traffic_data),
                websocket
            )
            
            # Wait 5 seconds before next update
            await asyncio.sleep(5)
            
    except Exception as e:
        logger.error(f"Error in traffic updates: {e}")

@websocket_router.websocket("/ws/sensors")
async def websocket_sensors_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time sensor data"""
    await manager.connect(websocket)
    try:
        # Start background task to send sensor updates
        asyncio.create_task(send_sensor_updates(websocket))
        
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            logger.info(f"Received sensor message: {message}")
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected from sensors WebSocket")
    except Exception as e:
        logger.error(f"Sensor WebSocket error: {e}")
        manager.disconnect(websocket)

async def send_sensor_updates(websocket: WebSocket):
    """Send periodic sensor data updates"""
    try:
        while websocket in manager.active_connections:
            sensor_data = {
                "type": "sensor_update",
                "timestamp": datetime.now().isoformat(),
                "sensors": [
                    {
                        "sensor_id": f"sensor_{i}",
                        "type": "traffic_counter",
                        "location": {
                            "lat": 26.4628 + random.uniform(-0.01, 0.01),
                            "lng": -81.773 + random.uniform(-0.01, 0.01)
                        },
                        "readings": {
                            "vehicle_count": random.randint(0, 20),
                            "avg_speed": random.randint(20, 50),
                            "occupancy": random.uniform(0.1, 0.8)
                        },
                        "status": "active"
                    }
                    for i in range(1, 8)  # 7 sensors
                ]
            }
            
            await manager.send_personal_message(
                json.dumps(sensor_data),
                websocket
            )
            
            await asyncio.sleep(3)  # Update every 3 seconds
            
    except Exception as e:
        logger.error(f"Error in sensor updates: {e}")

# Utility functions for broadcasting
async def broadcast_traffic_alert(alert_data: Dict[str, Any]):
    """Broadcast traffic alert to all connected clients"""
    message = {
        "type": "traffic_alert",
        "timestamp": datetime.now().isoformat(),
        "alert": alert_data
    }
    await manager.broadcast(json.dumps(message))

async def broadcast_system_status(status: str, details: str = ""):
    """Broadcast system status update"""
    message = {
        "type": "system_status",
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "details": details
    }
    await manager.broadcast(json.dumps(message))