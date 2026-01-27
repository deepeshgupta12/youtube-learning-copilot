"use client";

import * as React from "react";

export type TabItem = { key: string; label: string };

export function Tabs({
  items,
  value,
  onChange,
  className = "",
}: {
  items: TabItem[];
  value: string;
  onChange: (key: string) => void;
  className?: string;
}) {
  return (
    <div className={`tabs ${className}`}>
      {items.map((t) => (
        <button
          key={t.key}
          className={`tab ${value === t.key ? "tab-active" : ""}`}
          onClick={() => onChange(t.key)}
          type="button"
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}