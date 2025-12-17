import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cline X Sync",
  description: "Secure Remote Access Gateway",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased bg-gray-950 text-gray-100">{children}</body>
    </html>
  );
}
