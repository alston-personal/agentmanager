import type { Metadata } from "next";
import "./globals.css";
import StudioNavbar from "@/components/StudioNavbar";

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
      <body>
        <StudioNavbar />
        {children}
      </body>
    </html>
  );
}
