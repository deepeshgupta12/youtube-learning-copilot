import type { Metadata } from "next";
import "./globals.css";
import { AppHeader } from "../components/AppHeader";

export const metadata: Metadata = {
  title: "YouTube Learning Copilot",
  description: "Turn any YouTube video into a study pack: summary, takeaways, chapters, flashcards, and quiz.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="bg-noise" />
        <AppHeader />
        {children}
      </body>
    </html>
  );
}