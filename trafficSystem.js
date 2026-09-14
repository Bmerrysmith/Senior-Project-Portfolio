/**
 * FGCU Traffic System - Core JavaScript Modules
 * Enhanced traffic-viewer.html with signal-based sensors and road interaction
 */

// Traffic level definitions
const TRAFFIC_LEVELS = {
  HEAVY: "HEAVY",
  MODERATE: "MODERATE",
  LIGHT: "LIGHT",
  MINIMAL: "MINIMAL",
};

// Color mapping for traffic levels
function getTrafficColor(level) {
  const colors = {
    [TRAFFIC_LEVELS.HEAVY]: Cesium.Color.RED,
    [TRAFFIC_LEVELS.MODERATE]: Cesium.Color.ORANGE,
    [TRAFFIC_LEVELS.LIGHT]: Cesium.Color.YELLOW,
    [TRAFFIC_LEVELS.MINIMAL]: Cesium.Color.LIME,
  };
  return colors[level] || Cesium.Color.WHITE;
}

// Simple spatial indexing for roads
class RoadIndex {
  constructor() {
    this.roads = new Map();
    this.trafficData = new Map();
    this.spatialGrid = new Map();
    this.gridSize = 0.001; // Grid cell size in degrees (~100m)
    console.log("🗺️ RoadIndex initialized");
  }

  // Add road to index
  addRoad(road) {
    this.roads.set(road.id, road);

    // Add to spatial grid
    const gridKey = this.getGridKey(road.midpoint[0], road.midpoint[1]);
    if (!this.spatialGrid.has(gridKey)) {
      this.spatialGrid.set(gridKey, []);
    }
    this.spatialGrid.get(gridKey).push(road.id);

    console.log(`➕ Added road: ${road.name}`);
  }

  // Get spatial grid key
  getGridKey(lon, lat) {
    const gridX = Math.floor(lon / this.gridSize);
    const gridY = Math.floor(lat / this.gridSize);
    return `${gridX},${gridY}`;
  }

  // Find nearest road to point
  findNearest(lon, lat, maxDistanceMeters = 30) {
    const searchRadius = 2; // Search 2x2 grid around point
    const candidates = [];

    const centerGridX = Math.floor(lon / this.gridSize);
    const centerGridY = Math.floor(lat / this.gridSize);

    // Search neighboring grid cells
    for (let dx = -searchRadius; dx <= searchRadius; dx++) {
      for (let dy = -searchRadius; dy <= searchRadius; dy++) {
        const gridKey = `${centerGridX + dx},${centerGridY + dy}`;
        const cellRoads = this.spatialGrid.get(gridKey) || [];

        for (const roadId of cellRoads) {
          candidates.push(this.roads.get(roadId));
        }
      }
    }

    if (candidates.length === 0) return null;

    let nearestRoad = null;
    let nearestDistance = maxDistanceMeters;

    for (const road of candidates) {
      if (!road) continue;

      const distance = this.distanceToRoad(lon, lat, road);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestRoad = road;
      }
    }

    return nearestRoad;
  }

  // Calculate distance from point to road
  distanceToRoad(lon, lat, road) {
    const positions = road.positions;
    let minDistance = Infinity;

    // Check distance to each segment
    for (let i = 0; i < positions.length - 2; i += 2) {
      const x1 = positions[i];
      const y1 = positions[i + 1];
      const x2 = positions[i + 2];
      const y2 = positions[i + 3];

      const distance = this.pointToLineDistance(lon, lat, x1, y1, x2, y2);
      minDistance = Math.min(minDistance, distance);
    }

    // Convert to meters (rough approximation)
    return minDistance * 111320;
  }

  // Point to line segment distance
  pointToLineDistance(px, py, x1, y1, x2, y2) {
    const A = px - x1;
    const B = py - y1;
    const C = x2 - x1;
    const D = y2 - y1;

    const dot = A * C + B * D;
    const lenSq = C * C + D * D;

    if (lenSq === 0) {
      return Math.sqrt(A * A + B * B);
    }

    let param = dot / lenSq;
    param = Math.max(0, Math.min(1, param));

    const xx = x1 + param * C;
    const yy = y1 + param * D;

    const dx = px - xx;
    const dy = py - yy;

    return Math.sqrt(dx * dx + dy * dy);
  }

  // Create road from OSM data
  static fromOSMWay(way) {
    if (!way.geometry || way.geometry.length < 2) {
      throw new Error("Invalid OSM way geometry");
    }

    const positions = [];
    let minLon = Infinity,
      minLat = Infinity;
    let maxLon = -Infinity,
      maxLat = -Infinity;

    // Extract coordinates
    for (const point of way.geometry) {
      positions.push(point.lon, point.lat);
      minLon = Math.min(minLon, point.lon);
      minLat = Math.min(minLat, point.lat);
      maxLon = Math.max(maxLon, point.lon);
      maxLat = Math.max(maxLat, point.lat);
    }

    // Compute midpoint
    const midIdx = Math.floor(positions.length / 4) * 2;
    const midpoint = [positions[midIdx], positions[midIdx + 1]];

    // Compute length
    let length = 0;
    for (let i = 0; i < positions.length - 2; i += 2) {
      const lon1 = positions[i];
      const lat1 = positions[i + 1];
      const lon2 = positions[i + 2];
      const lat2 = positions[i + 3];

      const dLat = ((lat2 - lat1) * Math.PI) / 180;
      const dLon = ((lon2 - lon1) * Math.PI) / 180;
      const a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos((lat1 * Math.PI) / 180) *
          Math.cos((lat2 * Math.PI) / 180) *
          Math.sin(dLon / 2) *
          Math.sin(dLon / 2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
      length += 6371000 * c;
    }

    const tags = way.tags || {};

    return {
      id: `osm_way_${way.id}`,
      name: tags.name || tags.ref || `Unnamed ${tags.highway || "road"}`,
      kind: tags.highway || "unknown",
      positions,
      bbox: [minLon, minLat, maxLon, maxLat],
      length,
      midpoint,
      cesiumPositions: null, // Will be set later
      metadata: {
        lanes: tags.lanes ? parseInt(tags.lanes) : undefined,
        maxspeed: tags.maxspeed
          ? parseInt(tags.maxspeed.replace(/[^0-9]/g, ""))
          : undefined,
        surface: tags.surface,
        pci: null, // Will be joined later
      },
    };
  }

  // Load roads from OSM data
  async loadFromOSM(osmData) {
    console.log("📥 Loading roads from OSM data...");

    if (!osmData.elements) {
      throw new Error("Invalid OSM data format");
    }

    let roadCount = 0;
    for (const element of osmData.elements) {
      if (element.type === "way" && element.tags?.highway && element.geometry) {
        try {
          const road = RoadIndex.fromOSMWay(element);
          this.addRoad(road);
          roadCount++;
        } catch (error) {
          console.warn(`Failed to process OSM way ${element.id}:`, error);
        }
      }
    }

    console.log(`✅ Loaded ${roadCount} roads`);
    return roadCount;
  }

  // Get road by ID
  getRoad(id) {
    return this.roads.get(id);
  }

  // Get all roads
  getAllRoads() {
    return Array.from(this.roads.values());
  }

  // Set traffic data
  setTrafficData(roadId, metrics) {
    this.trafficData.set(roadId, metrics);
  }

  // Get traffic data
  getTrafficData(roadId) {
    return this.trafficData.get(roadId);
  }

  // Get statistics
  getStats() {
    return {
      roadCount: this.roads.size,
      trafficDataCount: this.trafficData.size,
    };
  }
}

// Traffic signal management
class SignalManager {
  constructor(viewer, roadIndex) {
    this.viewer = viewer;
    this.roadIndex = roadIndex;
    this.signals = [];
    this.signalEntities = new Map();
    console.log("🚦 SignalManager initialized");
  }

  // Add traffic signal
  addSignal(lon, lat, nearestRoad) {
    const signalId = `signal_${lon}_${lat}`;

    const entity = this.viewer.entities.add({
      id: signalId,
      name: `🚦 Traffic Signal • ${
        nearestRoad ? nearestRoad.name : "Unknown Road"
      }`,
      position: Cesium.Cartesian3.fromDegrees(lon, lat, 2), // Elevated 2m for visibility
      billboard: {
        image: this.createSignalIcon(),
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        scaleByDistance: new Cesium.NearFarScalar(50, 2.5, 5000, 1.0), // Much larger and visible from farther
        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY, // Always visible, never obscured
      },
      // Label removed - no more black dots from emoji outline
      properties: {
        type: "traffic_signal",
        roadId: nearestRoad ? nearestRoad.id : null,
        roadName: nearestRoad ? nearestRoad.name : "Unknown",
        lon: lon,
        lat: lat,
      },
    });

    const signal = {
      id: signalId,
      lon,
      lat,
      roadId: nearestRoad ? nearestRoad.id : null,
      roadName: nearestRoad ? nearestRoad.name : "Unknown",
      entity,
    };

    this.signals.push(signal);
    this.signalEntities.set(signalId, entity);

    console.log(
      `🚦 Added signal at ${
        nearestRoad ? nearestRoad.name : "unknown location"
      }`
    );
    return signal;
  }

  // Create enhanced signal icon SVG with better visibility
  createSignalIcon() {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48">
            <!-- Outer glow -->
            <circle cx="24" cy="24" r="20" fill="rgba(255,215,0,0.4)"/>
            <!-- Main circle with gradient -->
            <defs>
                <radialGradient id="signalGlow" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" style="stop-color:#FFFF00;stop-opacity:1" />
                    <stop offset="100%" style="stop-color:#FFD700;stop-opacity:1" />
                </radialGradient>
            </defs>
            <circle cx="24" cy="24" r="16" fill="url(#signalGlow)" stroke="#FF8800" stroke-width="3"/>
            <!-- Inner bright center -->
            <circle cx="24" cy="24" r="10" fill="#FFFF33"/>
            <!-- Center white highlight -->
            <circle cx="24" cy="24" r="4" fill="white"/>
        </svg>`;

    return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
  }

  // Load signals from OSM data
  async loadFromOSM(osmData) {
    console.log("🚦 Loading traffic signals from OSM...");

    let signalCount = 0;
    for (const element of osmData.elements) {
      if (
        element.type === "node" &&
        element.tags?.highway === "traffic_signals"
      ) {
        // Find nearest road within 25m
        const nearestRoad = this.roadIndex.findNearest(
          element.lon,
          element.lat,
          25
        );

        if (nearestRoad) {
          this.addSignal(element.lon, element.lat, nearestRoad);
          signalCount++;
        } else {
          console.warn(
            `Signal at ${element.lon}, ${element.lat} has no nearby road`
          );
        }
      }
    }

    console.log(`✅ Loaded ${signalCount} traffic signals`);
    return signalCount;
  }

  // Update signal pulse based on traffic
  updateSignalPulse(roadId, trafficLevel) {
    const roadsSignals = this.signals.filter((s) => s.roadId === roadId);

    for (const signal of roadsSignals) {
      if (trafficLevel === TRAFFIC_LEVELS.HEAVY) {
        // Add pulsing effect for heavy traffic
        signal.entity.billboard.color = Cesium.Color.fromAlpha(
          Cesium.Color.RED,
          0.8
        );
      } else {
        // Normal green color
        signal.entity.billboard.color = Cesium.Color.WHITE;
      }
    }
  }

  // Get signals for road
  getSignalsForRoad(roadId) {
    return this.signals.filter((s) => s.roadId === roadId);
  }
}

// Road selection and interaction
class RoadSelector {
  constructor(viewer, roadIndex, onRoadSelected) {
    this.viewer = viewer;
    this.roadIndex = roadIndex;
    this.onRoadSelected = onRoadSelected;
    this.selectedRoad = null;
    this.selectedEntity = null;
    this.setupClickHandler();
    console.log("👆 RoadSelector initialized");
  }

  // Setup click handler
  setupClickHandler() {
    this.viewer.cesiumWidget.screenSpaceEventHandler.setInputAction((event) => {
      this.handleClick(event);
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
  }

  // Handle click event
  handleClick(event) {
    const pickedObject = this.viewer.scene.pick(event.position);

    if (pickedObject && pickedObject.id) {
      const entity = pickedObject.id;

      // Check if clicked on signal
      if (entity.properties?.type?.getValue() === "traffic_signal") {
        const roadId = entity.properties.roadId?.getValue();
        if (roadId) {
          const road = this.roadIndex.getRoad(roadId);
          if (road) {
            this.selectRoad(road);
            return;
          }
        }
      }

      // Check if clicked on road entity
      if (entity.properties?.type?.getValue() === "road") {
        const roadId = entity.properties.roadId?.getValue();
        if (roadId) {
          const road = this.roadIndex.getRoad(roadId);
          if (road) {
            this.selectRoad(road);
            return;
          }
        }
      }
    }

    // No entity clicked, try ray picking for nearby roads
    const cartesian = this.viewer.camera.pickEllipsoid(
      event.position,
      this.viewer.scene.globe.ellipsoid
    );
    if (cartesian) {
      const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
      const lon = Cesium.Math.toDegrees(cartographic.longitude);
      const lat = Cesium.Math.toDegrees(cartographic.latitude);

      const nearestRoad = this.roadIndex.findNearest(lon, lat, 30);
      if (nearestRoad) {
        this.selectRoad(nearestRoad);
      } else {
        this.clearSelection();
      }
    }
  }

  // Select a road
  selectRoad(road) {
    this.clearSelection();

    this.selectedRoad = road;

    // Find the road entity and highlight it
    const entities = this.viewer.entities.values;
    for (const entity of entities) {
      if (entity.properties?.roadId?.getValue() === road.id) {
        // Highlight the road
        if (entity.polyline) {
          entity.polyline.width = 12;
          entity.polyline.material = new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.8,
            color: Cesium.Color.CYAN,
          });
          this.selectedEntity = entity;
        }
        break;
      }
    }

    // Notify callback
    if (this.onRoadSelected) {
      this.onRoadSelected(road);
    }

    console.log(`🛣️ Selected road: ${road.name}`);
  }

  // Clear selection
  clearSelection() {
    if (this.selectedEntity && this.selectedEntity.polyline) {
      // Restore original appearance
      const trafficData = this.roadIndex.getTrafficData(this.selectedRoad?.id);
      const color = trafficData
        ? getTrafficColor(trafficData.level)
        : Cesium.Color.GRAY;

      this.selectedEntity.polyline.width = this.getWidthForRoad(
        this.selectedRoad?.kind
      );
      this.selectedEntity.polyline.material =
        new Cesium.PolylineGlowMaterialProperty({
          glowPower: 0.4,
          color: color,
        });
    }

    this.selectedRoad = null;
    this.selectedEntity = null;

    if (this.onRoadSelected) {
      this.onRoadSelected(null);
    }
  }

  // Get width for road type
  getWidthForRoad(roadKind) {
    const widths = {
      trunk: 8,
      primary: 8,
      secondary: 6,
      tertiary: 6,
      residential: 3,
      service: 3,
    };
    return widths[roadKind] || 4;
  }

  // Get selected road
  getSelectedRoad() {
    return this.selectedRoad;
  }
}
