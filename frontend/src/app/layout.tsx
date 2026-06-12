import type { Metadata } from "next";
import { Inter, Roboto_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const robotoMono = Roboto_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "DeltaForge — Options Risk Terminal",
  description: "Options risk & delta-neutral hedging, computed by a real Wolfram kernel.",
};

// Runs before paint: applies the saved/system theme with NO flash, and suppresses
// the global color transition on first load (re-enabled after two frames).
const themeScript = `(function(){try{var t=localStorage.getItem('df-theme')||(window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');var d=document.documentElement;d.setAttribute('data-theme',t);d.classList.add('theme-preload');requestAnimationFrame(function(){requestAnimationFrame(function(){d.classList.remove('theme-preload');});});}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" className="theme-preload" suppressHydrationWarning>
      <body className={`${inter.variable} ${robotoMono.variable} antialiased min-h-screen`}>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
