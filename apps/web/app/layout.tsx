import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Tollgate",
  description: "Never get blindsided by a free-trial charge again."
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
