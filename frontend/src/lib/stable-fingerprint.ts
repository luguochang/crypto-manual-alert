type FingerprintObject = Record<string, unknown>;

/** Build a deterministic identity for validated JSON-like request values. */
export function stableFingerprint(value: unknown): string {
  return encodeValue(value, new WeakSet<object>());
}

function encodeValue(value: unknown, seen: WeakSet<object>): string {
  if (value === null) return "null";
  if (value === undefined) return "undefined";
  if (typeof value === "string") return `string:${value.length}:${value}`;
  if (typeof value === "number" || typeof value === "boolean") {
    return `${typeof value}:${String(value)}`;
  }
  if (typeof value !== "object") return `${typeof value}:${String(value)}`;
  if (seen.has(value)) throw new TypeError("Cannot fingerprint a cyclic value");
  seen.add(value);

  if (Array.isArray(value)) {
    const encoded = `[${value.map((item) => encodeValue(item, seen)).join(",")}]`;
    seen.delete(value);
    return encoded;
  }

  const object = value as FingerprintObject;
  const encoded = `{${Object.keys(object)
    .sort()
    .map((key) => `${encodeValue(key, seen)}:${encodeValue(object[key], seen)}`)
    .join(",")}}`;
  seen.delete(value);
  return encoded;
}
