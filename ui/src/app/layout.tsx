import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tainted — Forensic Evidence Dossier",
  description: "Chain of custody and decision reaffirmation ledger",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
