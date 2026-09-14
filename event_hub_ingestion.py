"""
Azure Event Hub Integration for Traffic Data Ingestion
Streams real-time traffic data to Azure Digital Twins
"""

from azure.eventhub import EventHubProducerClient, EventData
from azure.eventhub.aio import EventHubConsumerClient
from azure.identity import DefaultAzureCredential
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TrafficEventHubProducer:
    """Producer for sending traffic data to Event Hub"""
    
    def __init__(self, eventhub_namespace: str, eventhub_name: str):
        """
        Initialize Event Hub producer
        
        Args:
            eventhub_namespace: Event Hub namespace (e.g., 'fgcu-traffic')
            eventhub_name: Event Hub name (e.g., 'traffic-stream')
        """
        self.namespace = eventhub_namespace
        self.eventhub_name = eventhub_name
        
        # Use connection string in production
        # For demo, using DefaultAzureCredential
        connection_str = f"Endpoint=sb://{eventhub_namespace}.servicebus.windows.net/;" \
                        f"EntityPath={eventhub_name}"
        
        self.producer = EventHubProducerClient.from_connection_string(
            conn_str=connection_str,
            eventhub_name=eventhub_name
        )
        logger.info(f"✅ Event Hub Producer initialized for {eventhub_name}")
    
    async def send_traffic_event(self, traffic_data: Dict[str, Any]):
        """
        Send a single traffic event
        
        Args:
            traffic_data: Dictionary containing traffic metrics
        """
        event_data = EventData(json.dumps(traffic_data))
        
        # Add custom properties
        event_data.properties = {
            "timestamp": datetime.utcnow().isoformat(),
            "source": "fgcu-traffic-system",
            "event_type": "traffic_update"
        }
        
        async with self.producer:
            event_data_batch = await self.producer.create_batch()
            event_data_batch.add(event_data)
            await self.producer.send_batch(event_data_batch)
        
        logger.info(f"📤 Sent traffic event for road {traffic_data.get('road_id')}")
    
    async def send_traffic_batch(self, traffic_events: List[Dict[str, Any]]):
        """
        Send multiple traffic events in a batch
        
        Args:
            traffic_events: List of traffic data dictionaries
        """
        async with self.producer:
            event_data_batch = await self.producer.create_batch()
            
            for traffic_data in traffic_events:
                event_data = EventData(json.dumps(traffic_data))
                event_data.properties = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "fgcu-traffic-system"
                }
                
                try:
                    event_data_batch.add(event_data)
                except ValueError:
                    # Batch full, send and create new batch
                    await self.producer.send_batch(event_data_batch)
                    event_data_batch = await self.producer.create_batch()
                    event_data_batch.add(event_data)
            
            # Send remaining events
            if len(event_data_batch) > 0:
                await self.producer.send_batch(event_data_batch)
        
        logger.info(f"📤 Sent {len(traffic_events)} traffic events in batch")
    
    async def send_pavement_event(self, pavement_data: Dict[str, Any]):
        """
        Send pavement condition event
        
        Args:
            pavement_data: Dictionary containing PCI, IRI, condition data
        """
        event_data = EventData(json.dumps(pavement_data))
        event_data.properties = {
            "timestamp": datetime.utcnow().isoformat(),
            "source": "fgcu-pavement-system",
            "event_type": "pavement_condition"
        }
        
        async with self.producer:
            event_data_batch = await self.producer.create_batch()
            event_data_batch.add(event_data)
            await self.producer.send_batch(event_data_batch)
        
        logger.info(f"📤 Sent pavement event for asset {pavement_data.get('asset_id')}")
    
    def close(self):
        """Close the producer connection"""
        self.producer.close()
        logger.info("🔌 Event Hub Producer closed")


class TrafficEventHubConsumer:
    """Consumer for processing traffic events from Event Hub"""
    
    def __init__(self, eventhub_namespace: str, eventhub_name: str, 
                 consumer_group: str = "$Default"):
        """
        Initialize Event Hub consumer
        
        Args:
            eventhub_namespace: Event Hub namespace
            eventhub_name: Event Hub name
            consumer_group: Consumer group name
        """
        self.namespace = eventhub_namespace
        self.eventhub_name = eventhub_name
        self.consumer_group = consumer_group
        
        connection_str = f"Endpoint=sb://{eventhub_namespace}.servicebus.windows.net/;" \
                        f"EntityPath={eventhub_name}"
        
        self.consumer = EventHubConsumerClient.from_connection_string(
            conn_str=connection_str,
            consumer_group=consumer_group,
            eventhub_name=eventhub_name
        )
        logger.info(f"✅ Event Hub Consumer initialized for {eventhub_name}")
    
    async def process_events(self, callback_func):
        """
        Process incoming events
        
        Args:
            callback_func: Async function to handle each event
                          Should accept (partition_context, event) parameters
        """
        async def on_event(partition_context, event):
            try:
                # Parse event data
                event_data = json.loads(event.body_as_str())
                
                # Call user-provided callback
                await callback_func(event_data)
                
                # Update checkpoint
                await partition_context.update_checkpoint(event)
                
            except Exception as e:
                logger.error(f"❌ Error processing event: {e}")
        
        async with self.consumer:
            await self.consumer.receive(
                on_event=on_event,
                starting_position="-1"  # Start from beginning
            )
    
    def close(self):
        """Close the consumer connection"""
        self.consumer.close()
        logger.info("🔌 Event Hub Consumer closed")


# Integration with Azure Digital Twins
class EventHubToADTBridge:
    """Bridge between Event Hub and Azure Digital Twins"""
    
    def __init__(self, eventhub_namespace: str, eventhub_name: str, adt_client):
        """
        Initialize bridge
        
        Args:
            eventhub_namespace: Event Hub namespace
            eventhub_name: Event Hub name
            adt_client: ADTClient instance
        """
        self.consumer = TrafficEventHubConsumer(eventhub_namespace, eventhub_name)
        self.adt_client = adt_client
        logger.info("✅ Event Hub to ADT Bridge initialized")
    
    async def process_traffic_event(self, event_data: Dict[str, Any]):
        """
        Process traffic event and update ADT
        
        Args:
            event_data: Traffic event data
        """
        try:
            road_id = event_data.get("road_id")
            
            # Update ADT twin
            await self.adt_client.update_traffic_metrics(
                road_id=f"road-{road_id}",
                traffic_data={
                    "trafficLevel": event_data.get("traffic_level"),
                    "averageSpeed": event_data.get("average_speed"),
                    "vehicleCount": event_data.get("vehicle_count")
                }
            )
            
            # Send telemetry
            await self.adt_client.send_traffic_telemetry(
                road_id=f"road-{road_id}",
                telemetry_data=event_data
            )
            
            logger.info(f"✅ Processed traffic event for {road_id}")
            
        except Exception as e:
            logger.error(f"❌ Error processing traffic event: {e}")
    
    async def process_pavement_event(self, event_data: Dict[str, Any]):
        """
        Process pavement event and update ADT
        
        Args:
            event_data: Pavement event data
        """
        try:
            asset_id = event_data.get("asset_id")
            pci = event_data.get("pci")
            iri = event_data.get("iri")
            
            # Update ADT twin
            await self.adt_client.update_pavement_condition(
                pavement_id=f"pavement-{asset_id}",
                pci=pci,
                iri=iri
            )
            
            # Send telemetry
            await self.adt_client.send_pavement_telemetry(
                pavement_id=f"pavement-{asset_id}",
                pci=pci,
                iri=iri
            )
            
            logger.info(f"✅ Processed pavement event for {asset_id}")
            
        except Exception as e:
            logger.error(f"❌ Error processing pavement event: {e}")
    
    async def start_processing(self):
        """Start processing events from Event Hub"""
        logger.info("🚀 Starting Event Hub processing...")
        
        async def event_handler(event_data):
            event_type = event_data.get("event_type", "traffic_update")
            
            if event_type == "traffic_update":
                await self.process_traffic_event(event_data)
            elif event_type == "pavement_condition":
                await self.process_pavement_event(event_data)
        
        await self.consumer.process_events(event_handler)


# Example usage
if __name__ == "__main__":
    
    async def demo_producer():
        """Demo: Send sample traffic events"""
        producer = TrafficEventHubProducer(
            eventhub_namespace="fgcu-traffic",
            eventhub_name="traffic-stream"
        )
        
        # Sample traffic event
        traffic_event = {
            "road_id": "fgcu_blvd_001",
            "traffic_level": "MODERATE",
            "average_speed": 35,
            "vehicle_count": 150,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await producer.send_traffic_event(traffic_event)
        producer.close()
    
    async def demo_consumer():
        """Demo: Receive and process traffic events"""
        from adt_client import ADTClient
        
        adt_client = ADTClient("https://your-adt-instance.api.eus.digitaltwins.azure.net")
        
        bridge = EventHubToADTBridge(
            eventhub_namespace="fgcu-traffic",
            eventhub_name="traffic-stream",
            adt_client=adt_client
        )
        
        await bridge.start_processing()
    
    # Run demo
    asyncio.run(demo_producer())
