import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Command Center - Flight Deck",
  description: "Mission Control Dashboard for AI Projects",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
