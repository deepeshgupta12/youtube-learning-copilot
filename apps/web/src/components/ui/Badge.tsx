import * as React from "react";

type Tone = "neutral" | "good" | "warn" | "bad";

export function Badge({
  children,
  tone = "neutral",
  className = "",
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  const t =
    tone === "good"
      ? "badge badge-good"
      : tone === "warn"
      ? "badge badge-warn"
      : tone === "bad"
      ? "badge badge-bad"
      : "badge badge-neutral";

  return <span className={`${t} ${className}`}>{children}</span>;
}