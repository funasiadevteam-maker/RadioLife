// Phase Π.3 — Persistent footer with legal links.
import React from "react";
import { Link } from "react-router-dom";

export default function LegalFooter() {
  return (
    <footer data-testid="legal-footer"
                  className="border-t border-white/[0.06] mt-auto py-6 px-4
                                    text-[11px] text-text-secondary
                                    flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
      <span>© {new Date().getFullYear()} FUUSIC.app</span>
      <span data-testid="funasia-footer">part of{" "}
        <a href="https://funasianetwork.com" target="_blank" rel="noreferrer"
           data-testid="funasia-footer-link" className="underline hover:text-white">
          funasianetwork.com
        </a>
      </span>
      <Link to="/privacy" className="hover:text-white"
              data-testid="legal-footer-privacy">Privacy</Link>
      <Link to="/terms" className="hover:text-white"
              data-testid="legal-footer-terms">Terms</Link>
      <Link to="/cookies" className="hover:text-white"
              data-testid="legal-footer-cookies">Cookies</Link>
      <Link to="/dmca" className="hover:text-white"
              data-testid="legal-footer-dmca">DMCA</Link>
      <a href="mailto:hello@bigfantv.com" className="hover:text-white">Contact</a>
    </footer>
  );
}
