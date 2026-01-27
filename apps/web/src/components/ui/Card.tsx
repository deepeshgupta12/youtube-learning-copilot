import * as React from "react";

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <section className={`card ${className}`}>{children}</section>;
}

export function CardHeader({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
}) {
  return (
    <header className="card-header">
      <div style={{ minWidth: 0 }}>
        <div className="card-title">{title}</div>
        {subtitle ? <div className="card-subtitle">{subtitle}</div> : null}
      </div>
      {right ? <div className="card-right">{right}</div> : null}
    </header>
  );
}

export function CardBody({ children }: { children: React.ReactNode }) {
  return <div className="card-body">{children}</div>;
}