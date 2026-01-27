"use client";

import * as React from "react";

export function Input({
  label,
  hint,
  className = "",
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
}) {
  return (
    <label className={`field ${className}`}>
      {label ? <div className="field-label">{label}</div> : null}
      <input {...props} className="input" />
      {hint ? <div className="field-hint">{hint}</div> : null}
    </label>
  );
}