/**
 * RoadIndex - Spatial indexing system for FGCU road network
 * Provides fast nearest-road queries using simple spatial grid
 */

/// <reference path="../types/cesium.d.ts" />
/// <reference path="../../types/rbush.d.ts" />
import RBush from 'rbush';

export interface RoadSegment {
  id: string;
  name: string;
  kind: string; // highway type from OSM
  positions: number[]; // [lon, lat, lon, lat, ...] 
  cesiumPositions?: any[];
  bbox: [number, number, number, number]; // [minX, minY, maxX, maxY]
  length: number; // in meters
  midpoint: [number, number]; // [lon, lat]
  metadata?: {
    lanes?: number;
    maxspeed?: number;
    surface?: string;
    pci?: number; // Pavement Condition Index
  };
}

export interface TrafficMetrics {
  currentVolume: number; // vehicles/hour
  forecast1h: number;
  forecast4h: number;
  forecast24h: number;
  level: TrafficLevel;
  lastUpdated: string;
  signalCount: number;
}

export type TrafficLevel = 'HEAVY' | 'MODERATE' | 'LIGHT' | 'MINIMAL';

interface RTreeItem {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  roadId: string;
}

export class RoadIndex {
  private roads: Map<string, RoadSegment> = new Map();
  private spatialIndex: any = new RBush<RTreeItem>();
  private trafficData: Map<string, TrafficMetrics> = new Map();

  constructor() {
    console.log('🗺️ Initializing RoadIndex...');
  }

  /**
   * Add a road segment to the index
   */
  addRoad(segment: RoadSegment): void {
    this.roads.set(segment.id, segment);
    
    // Add to spatial index
    this.spatialIndex.insert({
      minX: segment.bbox[0],
      minY: segment.bbox[1], 
      maxX: segment.bbox[2],
      maxY: segment.bbox[3],
      roadId: segment.id
    });

    console.log(`➕ Added road: ${segment.name} (${segment.id})`);
  }

  /**
   * Find the nearest road segment to a point
   */
  findNearest(lon: number, lat: number, maxDistanceMeters: number = 30): RoadSegment | null {
    // Convert max distance to degrees (rough approximation)
    const maxDistanceDeg = maxDistanceMeters / 111320; // meters per degree at equator

    // Search in expanded bbox
    const searchBbox = {
      minX: lon - maxDistanceDeg,
      minY: lat - maxDistanceDeg,
      maxX: lon + maxDistanceDeg,
      maxY: lat + maxDistanceDeg
    };

    const candidates = this.spatialIndex.search(searchBbox);
    
    if (candidates.length === 0) {
      return null;
    }

    let nearestRoad: RoadSegment | null = null;
    let nearestDistance = maxDistanceMeters;

    // Check actual distance to each candidate
    for (const candidate of candidates) {
      const road = this.roads.get(candidate.roadId);
      if (!road) continue;

      const distance = this.distanceToRoad(lon, lat, road);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestRoad = road;
      }
    }

    return nearestRoad;
  }

  /**
   * Calculate distance from point to road segment
   */
  private distanceToRoad(lon: number, lat: number, road: RoadSegment): number {
    const positions = road.positions;
    let minDistance = Infinity;

    // Check distance to each segment of the polyline
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

  /**
   * Calculate point to line segment distance
   */
  private pointToLineDistance(px: number, py: number, x1: number, y1: number, x2: number, y2: number): number {
    const A = px - x1;
    const B = py - y1;
    const C = x2 - x1;
    const D = y2 - y1;

    const dot = A * C + B * D;
    const lenSq = C * C + D * D;
    
    if (lenSq === 0) {
      // Point to point distance
      return Math.sqrt(A * A + B * B);
    }

    let param = dot / lenSq;

    if (param < 0) {
      param = 0;
    } else if (param > 1) {
      param = 1;
    }

    const xx = x1 + param * C;
    const yy = y1 + param * D;
    
    const dx = px - xx;
    const dy = py - yy;
    
    return Math.sqrt(dx * dx + dy * dy);
  }

  /**
   * Get road by ID
   */
  getRoad(id: string): RoadSegment | null {
    return this.roads.get(id) || null;
  }

  /**
   * Get all roads
   */
  getAllRoads(): RoadSegment[] {
    return Array.from(this.roads.values());
  }

  /**
   * Update traffic data for a road
   */
  setTrafficData(roadId: string, metrics: TrafficMetrics): void {
    this.trafficData.set(roadId, metrics);
  }

  /**
   * Get traffic data for a road
   */
  getTrafficData(roadId: string): TrafficMetrics | null {
    return this.trafficData.get(roadId) || null;
  }

  /**
   * Create road segment from OSM way data
   */
  static fromOSMWay(way: any): RoadSegment {
    if (!way.geometry || way.geometry.length < 2) {
      throw new Error('Invalid OSM way geometry');
    }

    const positions: number[] = [];
    let minLon = Infinity, minLat = Infinity;
    let maxLon = -Infinity, maxLat = -Infinity;

    // Extract coordinates and compute bbox
    for (const point of way.geometry) {
      positions.push(point.lon, point.lat);
      minLon = Math.min(minLon, point.lon);
      minLat = Math.min(minLat, point.lat);
      maxLon = Math.max(maxLon, point.lon);
      maxLat = Math.max(maxLat, point.lat);
    }

    // Compute midpoint
    const midIdx = Math.floor(positions.length / 4) * 2;
    const midpoint: [number, number] = [positions[midIdx], positions[midIdx + 1]];

    // Compute approximate length
    let length = 0;
    for (let i = 0; i < positions.length - 2; i += 2) {
      const lon1 = positions[i];
      const lat1 = positions[i + 1];
      const lon2 = positions[i + 2];
      const lat2 = positions[i + 3];
      
      // Haversine distance approximation
      const dLat = (lat2 - lat1) * Math.PI / 180;
      const dLon = (lon2 - lon1) * Math.PI / 180;
      const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                Math.sin(dLon/2) * Math.sin(dLon/2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
      length += 6371000 * c; // Earth radius in meters
    }

    const tags = way.tags || {};
    
    return {
      id: `osm_way_${way.id}`,
      name: tags.name || tags.ref || `Unnamed ${tags.highway || 'road'}`,
      kind: tags.highway || 'unknown',
      positions,
      bbox: [minLon, minLat, maxLon, maxLat],
      length,
      midpoint,
      metadata: {
        lanes: tags.lanes ? parseInt(tags.lanes) : undefined,
        maxspeed: tags.maxspeed ? parseInt(tags.maxspeed.replace(/[^0-9]/g, '')) : undefined,
        surface: tags.surface
      }
    };
  }

  /**
   * Bulk load roads from OSM data
   */
  async loadFromOSM(osmData: any): Promise<void> {
    console.log('📥 Loading roads from OSM data...');
    
    if (!osmData.elements) {
      throw new Error('Invalid OSM data format');
    }

    let roadCount = 0;
    for (const element of osmData.elements) {
      if (element.type === 'way' && element.tags?.highway && element.geometry) {
        try {
          const road = RoadIndex.fromOSMWay(element);
          this.addRoad(road);
          roadCount++;
        } catch (error) {
          console.warn(`Failed to process OSM way ${element.id}:`, error);
        }
      }
    }

    console.log(`✅ Loaded ${roadCount} roads into spatial index`);
  }

  /**
   * Get index statistics
   */
  getStats(): { roadCount: number; indexSize: number; trafficDataCount: number } {
    return {
      roadCount: this.roads.size,
      indexSize: this.spatialIndex.all().length,
      trafficDataCount: this.trafficData.size
    };
  }
}

// Color utility for traffic levels
export const colorFor = (level: TrafficLevel): any => {
  const colors: Record<TrafficLevel, string> = {
    HEAVY: '#FF0000', // red
    MODERATE: '#FFA500', // orange
    LIGHT: '#FFFF00', // yellow
    MINIMAL: '#00FF00' // lime
  };
  return colors[level] || '#FFFFFF';
};

// Global road index instance
export const roadIndex = new RoadIndex();