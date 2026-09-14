// RBush spatial index type definitions

interface BBox {
    minX: number;
    minY: number;
    maxX: number;
    maxY: number;
}

interface RBushItem extends BBox {
    [key: string]: any;
}

declare class RBushClass<T extends RBushItem = RBushItem> {
    constructor(maxEntries?: number);
    
    insert(item: T): this;
    load(items: T[]): this;
    remove(item: T, equalsFn?: (a: T, b: T) => boolean): this;
    clear(): this;
    search(bbox: BBox): T[];
    collides(bbox: BBox): boolean;
    all(): T[];
    toJSON(): any;
    fromJSON(data: any): this;
}

declare module 'rbush' {
    const RBush: typeof RBushClass;
    export = RBush;
}