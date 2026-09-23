import { ImageResponse } from "next/og";

// Next ImageResponse renders outside the application stylesheet, so CSS custom
// properties and Tailwind theme tokens are unavailable here. These values mirror
// the canonical palette in tokens.css; this is the sole raw-color exception.

export const alt = "SecondTrip — make repeat visits easier to understand";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    <div
      style={{
        alignItems: "stretch",
        background: "#f6f8f7",
        color: "#172b2f",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        justifyContent: "space-between",
        padding: "72px 82px",
        width: "100%",
      }}
    >
      <div style={{ color: "#0b7a75", display: "flex", fontSize: 28, fontWeight: 700 }}>
        SecondTrip
      </div>
      <div style={{ display: "flex", flexDirection: "column", maxWidth: 930 }}>
        <div style={{ color: "#12343b", display: "flex", fontSize: 66, fontWeight: 700 }}>
          Make repeat visits easier to understand.
        </div>
        <div style={{ display: "flex", fontSize: 30, lineHeight: 1.5, marginTop: 28 }}>
          Import job history · surface possible callbacks · review the evidence · record the decision
        </div>
      </div>
      <div style={{ alignItems: "center", display: "flex", gap: 18 }}>
        {["First visit", "Return visit", "Human review"].map((label, index) => (
          <div key={label} style={{ alignItems: "center", display: "flex", gap: 12 }}>
            {index > 0 ? <div style={{ background: "#d8e2e1", height: 2, width: 72 }} /> : null}
            <div style={{ background: index === 2 ? "#f2b36d" : "#0b7a75", borderRadius: 12, height: 18, width: 18 }} />
            <div style={{ display: "flex", fontSize: 22 }}>{label}</div>
          </div>
        ))}
      </div>
    </div>,
    size,
  );
}
