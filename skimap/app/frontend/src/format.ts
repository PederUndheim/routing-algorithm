/** A distance along a route, always in km so a column of them lines up. */
export const km = (metres: number): string => (metres / 1000).toFixed(2) + " km";

/** A stretch's length: metres under a kilometre, where most Danger zones
 *  are, km above. */
export const stretchLength = (metres: number): string =>
  metres < 1000 ? `${Math.round(metres)} m` : km(metres);
