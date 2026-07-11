const REDACTED = "[REDACTED]";

const SECRET_KEY_PATTERN =
  /(^|[_\-.])(api[_\-.]?key|token|secret|authorization|device[_\-.]?key|bark[_\-.]?device[_\-.]?key|access[_\-.]?key|private[_\-.]?key|client[_\-.]?secret)($|[_\-.])/i;

const SECRET_TEXT_REPLACEMENTS: Array<[RegExp, string]> = [
  [/https:\/\/api\.day\.app\/[^\s"'<>]+/gi, "https://api.day.app/[REDACTED]"],
  [/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [REDACTED]"],
  [/\b(BARK_DEVICE_KEY|BARK[-_\s]?DEVICE[-_\s]?KEY)\s*[:=]\s*[^\s,;'"<>]+/gi, "$1=[REDACTED]"],
  [/([?&](?:token|api_key|apikey|device_key|deviceKey|key)=)[^&\s"'<>]+/gi, "$1[REDACTED]"]
];

function formatJson(value: unknown) {
  const redacted = redactJsonForDisplay(value);
  return typeof redacted === "string" ? redacted : JSON.stringify(redacted ?? null, null, 2);
}

function redactJsonForDisplay(value: unknown): unknown {
  return redactValue(value, new WeakSet<object>());
}

function redactValue(value: unknown, seen: WeakSet<object>): unknown {
  if (typeof value === "string") {
    return redactSecretText(value);
  }
  if (Array.isArray(value)) {
    if (seen.has(value)) return "[Circular]";
    seen.add(value);
    return value.map((item) => redactValue(item, seen));
  }
  if (value && typeof value === "object") {
    if (seen.has(value)) return "[Circular]";
    seen.add(value);
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [
        key,
        isSecretKey(key) ? REDACTED : redactValue(item, seen)
      ])
    );
  }
  return value;
}

function redactSecretText(value: string): string {
  return SECRET_TEXT_REPLACEMENTS.reduce((current, [pattern, replacement]) => {
    return current.replace(pattern, replacement);
  }, value);
}

function isSecretKey(key: string): boolean {
  return SECRET_KEY_PATTERN.test(key);
}

export function JsonDetails({
  title,
  value,
  large = false,
  light = false,
}: {
  title: string;
  value: unknown;
  large?: boolean;
  light?: boolean;
}) {
  const className = ["code-box", large ? "large-code" : "", light ? "light-code" : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <details className="trace-step json-details" role="group" aria-label={`${title} JSON`}>
      <summary>
        <span>{title}</span>
        <span>JSON</span>
      </summary>
      <pre className={className}>{formatJson(value)}</pre>
    </details>
  );
}

export { formatJson, redactJsonForDisplay };
