import type { Metadata } from "next";
import type { ReactNode } from "react";

import { BASE_PATH } from "@/lib/constants";
import { QueryProvider } from "@/lib/query/provider";

import "./globals.css";

export const metadata: Metadata = {
  title: "MetaTracer",
  description: "Authorized metadata discovery",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // theme-init.js sets data-theme before hydration; the server renders the dark default.
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        {/* Blocking on purpose: avoids a flash of the wrong theme. Served from 'self'. */}
        <script src={`${BASE_PATH}/theme-init.js`} />
      </head>
      <body>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
