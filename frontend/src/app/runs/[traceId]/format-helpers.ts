export function shortHash(value: string | null | undefined) {
  if (!value) return "-";
  return value.length > 16 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value;
}

export function valueText(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    const scalars = value.filter((item) => ["string", "number", "boolean"].includes(typeof item)).slice(0, 4).map(String);
    return scalars.length > 0 ? scalars.join(", ") : "结构化列表已记录";
  }
  return "结构化内容已记录";
}

export function metricText(value: number | null | undefined, suffix = "") {
  if (value === null || value === undefined) return "-";
  return `${value}${suffix}`;
}

export function moneyText(value: number | null | undefined) {
  if (value === null || value === undefined) return "unknown";
  return `$${value.toFixed(6)}`;
}

export function fieldText(record: Record<string, unknown> | undefined, key: string) {
  if (!record) return "-";
  return valueText(record[key]);
}
