import { formatJson } from "@/app/shared/json-details";

export function shortHash(value: string | null | undefined) {
  if (!value) return "-";
  return value.length > 16 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value;
}

export function valueText(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return formatJson(value);
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
  const value = record[key];
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}
