import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";
import "@xyflow/react/dist/style.css";
import "mapbox-gl/dist/mapbox-gl.css";

export const metadata: Metadata = {
  title: "SHADOW INTERNET | Infrastructure intelligence",
  description: "Reveal the hidden infrastructure powering the internet. Evidence-based DNS, TLS and provider dependency intelligence.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const content = <html lang="en"><body>{children}</body></html>;
  return process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ? <ClerkProvider>{content}</ClerkProvider> : content;
}
