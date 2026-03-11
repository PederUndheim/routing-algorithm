export type CorridorBounds = {
  west: number;
  south: number;
  east: number;
  north: number;
};

export type CorridorMode = "conservative" | "balanced" | "explorative";

export type CorridorVariantUrls = Partial<Record<CorridorMode, string>>;
