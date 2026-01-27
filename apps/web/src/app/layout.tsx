import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "YouTube Learning Copilot",
  description: "Turn any YouTube video into a clean study pack: summary, takeaways, chapters, flashcards, and quiz.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <div className="app-bg">
          <div className="app-noise" />
          <div className="app-shell">
            <header className="app-header">
              <div className="brand">
                <div className="brand-dot" />
                <div className="brand-text">
                  <div className="brand-title">YouTube Learning Copilot</div>
                  <div className="brand-subtitle">Study packs from any video transcript</div>
                </div>
              </div>

              <div className="header-right">
                <span className="pill">Local</span>
                <span className="pill subtle">Glass UI</span>
              </div>
            </header>

            {children}

            <footer className="app-footer">
              <div className="footer-left">
                <span className="muted">API:</span>{" "}
                <span className="mono">{process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}</span>
              </div>
              <div className="footer-right muted">Built for fast learning.</div>
            </footer>
          </div>
        </div>
      </body>
    </html>
  );
}