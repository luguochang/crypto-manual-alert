function formatJson(value: unknown) {
  return JSON.stringify(value ?? null, null, 2);
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
    <details className="trace-step json-details">
      <summary>
        <span>{title}</span>
        <span>JSON</span>
      </summary>
      <pre className={className}>{typeof value === "string" ? value : formatJson(value)}</pre>
    </details>
  );
}

export { formatJson };
