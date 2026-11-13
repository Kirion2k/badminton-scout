import type { Metadata, Viewport } from "next";
import { Barlow, Barlow_Condensed } from "next/font/google";
import "./globals.css";

// Barlow for reading, Barlow Condensed for competition headings, scores and labels
const barlow = Barlow({
  variable: "--font-barlow",
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "600"],
});

const barlowCondensed = Barlow_Condensed({
  variable: "--font-barlow-condensed",
  subsets: ["latin", "latin-ext"],
  weight: ["500", "600", "700"],
});

export const viewport: Viewport = { themeColor: "#0b1526" };

export const metadata: Metadata = {
  title: { default: "Badminton Scout", template: "%s · Badminton Scout" },
  description:
    "Badminton match records and player profiles, with every number traced to its source.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${barlow.variable} ${barlowCondensed.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-lime focus:px-3 focus:py-2 focus:text-night"
        >
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
