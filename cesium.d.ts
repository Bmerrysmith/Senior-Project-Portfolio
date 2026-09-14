// Cesium type definitions for our project
declare namespace Cesium {
  class Cartesian3 {
    x: number;
    y: number;
    z: number;
    constructor(x?: number, y?: number, z?: number);
    static fromDegrees(longitude: number, latitude: number, height?: number): Cartesian3;
    static fromDegreesArray(coordinates: number[]): Cartesian3[];
  }

  class Color {
    red: number;
    green: number;
    blue: number;
    alpha: number;
    static RED: Color;
    static ORANGE: Color;
    static YELLOW: Color;
    static LIME: Color;
    static WHITE: Color;
    constructor(red?: number, green?: number, blue?: number, alpha?: number);
  }
}

// RBush spatial index types
declare class RBush<T = any> {
  constructor(maxEntries?: number);
  insert(item: T): this;
  search(bbox: { minX: number; minY: number; maxX: number; maxY: number }): T[];
  remove(item: T): this;
  clear(): this;
}

export {};