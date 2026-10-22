// The worker's peak-tile cache: fetch what the painter reported missing, keep
// the most recent tiles, never ask for the same tile twice at once, and do not
// hammer a tile that failed. Tiles never change (their ETag is the content's
// key), so the browser's own HTTP cache sits underneath this one.

const MAX_TILES = 600; // 8 KB each: about 5 MB
const MAX_INFLIGHT = 6;
const RETRY_MS = 5000;

export function createTileStore({
  fetchTile,
  onChange,
  maxTiles = MAX_TILES,
  maxInflight = MAX_INFLIGHT,
  retryMs = RETRY_MS,
  now = () => Date.now(),
}) {
  const tiles = new Map(); // key -> Float32Array | { pending } | { failedAt }
  const queue = [];
  let inflight = 0;

  const key = (media, level, tile) => `${media}/${level}/${tile}`;

  // Oldest first, tiles and failures alike (a failure forgotten is only retried sooner). A
  // failure used to stay for good, so tiles that keep failing grew the map without bound, and
  // past the bound each fetched tile was evicted on arrival. Pending entries stay: their fetch
  // is under way and will land.
  function evict() {
    for (const [name, value] of tiles) {
      if (tiles.size <= maxTiles) return;
      if (!value.pending) tiles.delete(name);
    }
  }

  function pump() {
    while (inflight < maxInflight && queue.length > 0) {
      const { media, level, tile } = queue.shift();
      const name = key(media, level, tile);
      inflight += 1;
      fetchTile(media, level, tile)
        // Delete first: Map.set on a key keeps its old place, and the pending entry was made
        // when the tile was asked for, so the arrival would count as old.
        .then((data) => {
          tiles.delete(name);
          tiles.set(name, data);
          evict();
        })
        .catch(() => {
          tiles.delete(name);
          tiles.set(name, { failedAt: now() });
          evict();
        })
        .finally(() => {
          inflight -= 1;
          onChange();
          pump();
        });
    }
  }

  return {
    /** Entries held (tiles, pending fetches, remembered failures). */
    size: () => tiles.size,
    lookup(media, level, tile) {
      const name = key(media, level, tile);
      const value = tiles.get(name);
      if (!(value instanceof Float32Array)) return undefined;
      tiles.delete(name); // re-insert: most recently used last
      tiles.set(name, value);
      return value;
    },
    want(list) {
      for (const item of list) {
        const name = key(item.media, item.level, item.tile);
        const known = tiles.get(name);
        if (known instanceof Float32Array || known?.pending) continue;
        if (known && now() - known.failedAt < retryMs) continue;
        tiles.set(name, { pending: true });
        queue.push(item);
      }
      pump();
    },
  };
}
