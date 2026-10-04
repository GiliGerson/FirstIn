import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ variable: "--font-sans-family", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "FirstIn — be first in line for student tech jobs",
  description:
    "FirstIn scans Israeli company career sites and LinkedIn for student, part-time and internship tech roles, " +
    "ranks every job against your profile, and sends the best ones to Telegram.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" dir="ltr" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full font-sans">{children}</body>
    </html>
  );
}
