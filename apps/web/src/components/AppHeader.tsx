import Link from "next/link";
import { Badge } from "./ui/Badge";

export function AppHeader() {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link href="/" className="brand">
          <span className="brand-dot" />
          <div className="brand-text">
            <div className="brand-title">YouTube Learning Copilot</div>
            <div className="brand-subtitle">Study packs from any video transcript</div>
          </div>
        </Link>

        <div className="topbar-right">
          <Badge>Local</Badge>
          <Badge tone="good">Glass UI</Badge>
        </div>
      </div>
    </header>
  );
}