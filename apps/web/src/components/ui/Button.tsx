"use client";

import * as React from "react";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md";

export function Button({
  children,
  className = "",
  variant = "primary",
  size = "md",
  disabled,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
}) {
  const v =
    variant === "primary"
      ? "btn btn-primary"
      : variant === "secondary"
      ? "btn btn-secondary"
      : "btn btn-ghost";

  const s = size === "sm" ? "btn-sm" : "btn-md";

  return (
    <button
      {...props}
      disabled={disabled}
      className={`${v} ${s} ${disabled ? "btn-disabled" : ""} ${className}`}
    >
      {children}
    </button>
  );
}