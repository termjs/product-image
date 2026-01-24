import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const geistSans = localFont({
  src: [
    {
      path: "./Geist-Regular.ttf",
      weight: "400",
      style: "normal",
    },
    {
      path: "./Geist-SemiBold.ttf",
      weight: "600",
      style: "normal",
    },
  ],
  variable: "--font-geist-sans",
});

export const metadata: Metadata = {
  title: "Product Image Processor",
  description:
    "Standardize product images with precision. Create templates and process images to match exact specifications automatically.",
  openGraph: {
    title: "Product Image Processor",
    description:
      "Standardize product images with precision. Create templates and process images to match exact specifications automatically.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} antialiased`}>{children}</body>
    </html>
  );
}
