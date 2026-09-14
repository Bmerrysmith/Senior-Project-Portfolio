"""
Azure Digital Twins Integration Client
Handles all ADT operations for FGCU Traffic System
"""

from azure.digitaltwins.core import DigitalTwinsClient
from azure.identity import DefaultAzureCredential
from typing import Dict, List, Optional, Any
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ADTClient:
    """Azure Digital Twins client for traffic system integration"""
    
    def __init__(self, adt_endpoint: str):
        """
        Initialize ADT client with endpoint
        
        Args:
            adt_endpoint: Azure Digital Twins instance URL
                         (e.g., "https://your-adt-instance.api.eus.digitaltwins.azure.net")
        """
        self.endpoint = adt_endpoint
        self.credential = DefaultAzureCredential()
        self.client = DigitalTwinsClient(self.endpoint, self.credential)
        logger.info(f"✅ ADT Client initialized for {adt_endpoint}")
    
    # ==================== TWIN OPERATIONS ====================
    
    async def create_road_twin(self, road_data: Dict[str, Any]) -> Dict:
        """
        Create a road digital twin in ADT
        
        Args:
            road_data: Dictionary containing road properties
        
        Returns:
            Created twin object
        """
        twin_id = f"road-{road_data.get('id', 'unknown')}"
        
        digital_twin = {
            "$metadata": {
                "$model": "dtmi:fgcu:Road;1"
            },
            "$dtId": twin_id,
            "name": road_data.get("name"),
            "roadType": road_data.get("roadType", "local"),
            "length": road_data.get("length"),
            "coordinates": road_data.get("coordinates"),
            "trafficLevel": road_data.get("trafficLevel", "LIGHT"),
            "averageSpeed": road_data.get("averageSpeed", 0),
            "vehicleCount": road_data.get("vehicleCount", 0)
        }
        
        created_twin = self.client.upsert_digital_twin(twin_id, digital_twin)
        logger.info(f"✅ Created road twin: {twin_id}")
        return created_twin
    
    async def create_sensor_twin(self, sensor_data: Dict[str, Any]) -> Dict:
        """
        Create a traffic sensor digital twin in ADT
        
        Args:
            sensor_data: Dictionary containing sensor properties
        
        Returns:
            Created twin object
        """
        twin_id = f"sensor-{sensor_data.get('id', 'unknown')}"
        
        digital_twin = {
            "$metadata": {
                "$model": "dtmi:fgcu:TrafficSensor;1"
            },
            "$dtId": twin_id,
            "sensorId": sensor_data.get("sensorId"),
            "sensorType": sensor_data.get("sensorType", "traffic_signal"),
            "status": sensor_data.get("status", "active"),
            "location": {
                "latitude": sensor_data.get("latitude"),
                "longitude": sensor_data.get("longitude")
            }
        }
        
        created_twin = self.client.upsert_digital_twin(twin_id, digital_twin)
        logger.info(f"✅ Created sensor twin: {twin_id}")
        return created_twin
    
    async def create_pavement_twin(self, pavement_data: Dict[str, Any]) -> Dict:
        """
        Create a pavement asset digital twin in ADT
        
        Args:
            pavement_data: Dictionary containing pavement properties
        
        Returns:
            Created twin object
        """
        twin_id = f"pavement-{pavement_data.get('id', 'unknown')}"
        
        digital_twin = {
            "$metadata": {
                "$model": "dtmi:fgcu:PavementAsset;1"
            },
            "$dtId": twin_id,
            "assetId": pavement_data.get("assetId"),
            "roadSegmentId": pavement_data.get("roadSegmentId"),
            "pci": pavement_data.get("pci", 75),
            "iri": pavement_data.get("iri", 100.0),
            "surfaceType": pavement_data.get("surfaceType", "asphalt"),
            "condition": pavement_data.get("condition", "good"),
            "lastInspectionDate": pavement_data.get("lastInspectionDate"),
            "estimatedRemainingLife": pavement_data.get("estimatedRemainingLife", 10),
            "reconstructionPriority": pavement_data.get("reconstructionPriority", 5)
        }
        
        created_twin = self.client.upsert_digital_twin(twin_id, digital_twin)
        logger.info(f"✅ Created pavement twin: {twin_id}")
        return created_twin
    
    # ==================== RELATIONSHIP OPERATIONS ====================
    
    async def create_relationship(self, source_id: str, target_id: str, 
                                  relationship_name: str, relationship_id: Optional[str] = None) -> Dict:
        """
        Create a relationship between two twins
        
        Args:
            source_id: Source twin ID
            target_id: Target twin ID
            relationship_name: Name of the relationship (e.g., 'hasSensor', 'belongsToRoad')
            relationship_id: Optional custom relationship ID
        
        Returns:
            Created relationship object
        """
        if not relationship_id:
            relationship_id = f"{source_id}-{relationship_name}-{target_id}"
        
        relationship = {
            "$relationshipId": relationship_id,
            "$sourceId": source_id,
            "$relationshipName": relationship_name,
            "$targetId": target_id
        }
        
        created_rel = self.client.upsert_relationship(source_id, relationship_id, relationship)
        logger.info(f"✅ Created relationship: {source_id} -> {relationship_name} -> {target_id}")
        return created_rel
    
    # ==================== UPDATE OPERATIONS ====================
    
    async def update_traffic_metrics(self, road_id: str, traffic_data: Dict[str, Any]) -> Dict:
        """
        Update traffic metrics for a road twin
        
        Args:
            road_id: Road twin ID
            traffic_data: Dictionary with traffic metrics (trafficLevel, averageSpeed, vehicleCount)
        
        Returns:
            Updated twin
        """
        patch = [
            {
                "op": "replace",
                "path": "/trafficLevel",
                "value": traffic_data.get("trafficLevel")
            },
            {
                "op": "replace",
                "path": "/averageSpeed",
                "value": traffic_data.get("averageSpeed")
            },
            {
                "op": "replace",
                "path": "/vehicleCount",
                "value": traffic_data.get("vehicleCount")
            },
            {
                "op": "replace",
                "path": "/lastUpdated",
                "value": datetime.utcnow().isoformat()
            }
        ]
        
        self.client.update_digital_twin(road_id, patch)
        logger.info(f"✅ Updated traffic metrics for {road_id}")
        return {"status": "success", "road_id": road_id}
    
    async def update_pavement_condition(self, pavement_id: str, pci: int, iri: float) -> Dict:
        """
        Update pavement condition metrics
        
        Args:
            pavement_id: Pavement twin ID
            pci: Pavement Condition Index (0-100)
            iri: International Roughness Index
        
        Returns:
            Update status
        """
        # Determine condition category
        if pci >= 80:
            condition = "excellent"
        elif pci >= 70:
            condition = "good"
        elif pci >= 60:
            condition = "fair"
        else:
            condition = "poor"
        
        patch = [
            {"op": "replace", "path": "/pci", "value": pci},
            {"op": "replace", "path": "/iri", "value": iri},
            {"op": "replace", "path": "/condition", "value": condition}
        ]
        
        self.client.update_digital_twin(pavement_id, patch)
        logger.info(f"✅ Updated pavement condition for {pavement_id}: PCI={pci}, IRI={iri}")
        return {"status": "success", "pavement_id": pavement_id, "pci": pci}
    
    # ==================== QUERY OPERATIONS ====================
    
    async def query_roads_by_traffic_level(self, traffic_level: str) -> List[Dict]:
        """
        Query roads by traffic level
        
        Args:
            traffic_level: Traffic level (HEAVY, MODERATE, LIGHT, MINIMAL, LOW)
        
        Returns:
            List of matching road twins
        """
        query = f"""
        SELECT road
        FROM DIGITALTWINS road
        WHERE IS_OF_MODEL(road, 'dtmi:fgcu:Road;1')
        AND road.trafficLevel = '{traffic_level}'
        """
        
        results = list(self.client.query_twins(query))
        logger.info(f"📊 Found {len(results)} roads with traffic level {traffic_level}")
        return results
    
    async def query_pavement_by_condition(self, min_pci: int = 0, max_pci: int = 100) -> List[Dict]:
        """
        Query pavement assets by PCI range
        
        Args:
            min_pci: Minimum PCI score
            max_pci: Maximum PCI score
        
        Returns:
            List of matching pavement twins
        """
        query = f"""
        SELECT pavement
        FROM DIGITALTWINS pavement
        WHERE IS_OF_MODEL(pavement, 'dtmi:fgcu:PavementAsset;1')
        AND pavement.pci >= {min_pci}
        AND pavement.pci <= {max_pci}
        ORDER BY pavement.pci ASC
        """
        
        results = list(self.client.query_twins(query))
        logger.info(f"📊 Found {len(results)} pavement assets with PCI {min_pci}-{max_pci}")
        return results
    
    async def query_road_with_sensors(self, road_id: str) -> Dict:
        """
        Query road with all its sensors
        
        Args:
            road_id: Road twin ID
        
        Returns:
            Road twin with sensors
        """
        query = f"""
        SELECT road, sensor
        FROM DIGITALTWINS road
        JOIN sensor RELATED road.hasSensor
        WHERE road.$dtId = '{road_id}'
        AND IS_OF_MODEL(road, 'dtmi:fgcu:Road;1')
        AND IS_OF_MODEL(sensor, 'dtmi:fgcu:TrafficSensor;1')
        """
        
        results = list(self.client.query_twins(query))
        logger.info(f"📊 Queried road {road_id} with sensors")
        return results
    
    async def query_congested_roads(self, min_vehicle_count: int = 200) -> List[Dict]:
        """
        Query roads with high congestion
        
        Args:
            min_vehicle_count: Minimum vehicle count threshold
        
        Returns:
            List of congested roads
        """
        query = f"""
        SELECT road
        FROM DIGITALTWINS road
        WHERE IS_OF_MODEL(road, 'dtmi:fgcu:Road;1')
        AND road.vehicleCount >= {min_vehicle_count}
        ORDER BY road.vehicleCount DESC
        """
        
        results = list(self.client.query_twins(query))
        logger.info(f"📊 Found {len(results)} congested roads")
        return results
    
    # ==================== TELEMETRY OPERATIONS ====================
    
    async def send_traffic_telemetry(self, road_id: str, telemetry_data: Dict[str, Any]):
        """
        Send traffic telemetry to a road twin
        
        Args:
            road_id: Road twin ID
            telemetry_data: Telemetry payload
        """
        telemetry = {
            "timestamp": datetime.utcnow().isoformat(),
            "vehicleCount": telemetry_data.get("vehicleCount"),
            "averageSpeed": telemetry_data.get("averageSpeed"),
            "trafficLevel": telemetry_data.get("trafficLevel")
        }
        
        self.client.publish_telemetry(road_id, telemetry)
        logger.info(f"📡 Sent telemetry for {road_id}")
    
    async def send_pavement_telemetry(self, pavement_id: str, pci: int, iri: float):
        """
        Send pavement condition telemetry
        
        Args:
            pavement_id: Pavement twin ID
            pci: Current PCI value
            iri: Current IRI value
        """
        telemetry = {
            "pciTrend": {
                "timestamp": datetime.utcnow().isoformat(),
                "pciValue": pci
            },
            "iriTrend": {
                "timestamp": datetime.utcnow().isoformat(),
                "iriValue": iri
            }
        }
        
        self.client.publish_telemetry(pavement_id, telemetry)
        logger.info(f"📡 Sent pavement telemetry for {pavement_id}")
    
    # ==================== UTILITY OPERATIONS ====================
    
    async def get_twin(self, twin_id: str) -> Dict:
        """Get a digital twin by ID"""
        twin = self.client.get_digital_twin(twin_id)
        return twin
    
    async def delete_twin(self, twin_id: str):
        """Delete a digital twin"""
        self.client.delete_digital_twin(twin_id)
        logger.info(f"🗑️ Deleted twin: {twin_id}")
    
    async def get_all_twins_count(self) -> int:
        """Get total count of all twins"""
        query = "SELECT COUNT() FROM DIGITALTWINS"
        results = list(self.client.query_twins(query))
        return results[0].get("COUNT", 0) if results else 0


# Example usage
if __name__ == "__main__":
    import asyncio
    
    # Configuration
    ADT_ENDPOINT = "https://your-adt-instance.api.eus.digitaltwins.azure.net"
    
    async def main():
        # Initialize client
        adt = ADTClient(ADT_ENDPOINT)
        
        # Create sample road twin
        road_data = {
            "id": "fgcu_blvd_001",
            "name": "FGCU Boulevard",
            "roadType": "arterial",
            "length": 1200.5,
            "coordinates": [
                {"latitude": 26.4628, "longitude": -81.7730}
            ],
            "trafficLevel": "MODERATE",
            "averageSpeed": 35,
            "vehicleCount": 150
        }
        await adt.create_road_twin(road_data)
        
        # Query congested roads
        congested = await adt.query_congested_roads(min_vehicle_count=100)
        print(f"Found {len(congested)} congested roads")
    
    asyncio.run(main())
