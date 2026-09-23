type JsonLdValue = Record<string, unknown> | readonly Record<string, unknown>[];

function serializeJsonLd(value: JsonLdValue): string {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

export function JsonLd({ data }: { data: JsonLdValue }) {
  return <script type="application/ld+json">{serializeJsonLd(data)}</script>;
}
