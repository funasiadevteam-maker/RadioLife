/**
 * SignInWithGoogleButton  (Phase AUTH.1)
 * ----------------------------------------------------------------
 * Launches Google Sign-In via OUR OWN Google OAuth client (server-side
 * auth-code flow). Navigates to:
 *     {window.location.origin}/api/auth/google/login?return_to=...
 * The backend 302s to Google's consent screen (branded with the app's
 * own name), then sets our session cookie and bounces back into the app.
 *
 * Props
 *     size:            "small" | "medium" | "large"    (default "medium")
 *     variant:        "auto"    | "legacy" | "radiolife"      (default "auto")
 *     redirectPath: string — the in-app path to land on after login.
 *     onBeforeRedirect: () => void — optional analytics hook
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS,
 *                    THIS BREAKS THE AUTH.
 */
import { useCallback } from "react";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const GoogleGlyph = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden>
    <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.6-6 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.2-.1-2.4-.4-3.5z"/>
    <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 16 19 13 24 13c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
    <path fill="#4CAF50" d="M24 44c5.2 0 9.8-2 13.4-5.2l-6.2-5.2c-1.8 1.3-4.2 2.4-7.2 2.4-5.3 0-9.7-3.4-11.3-8L6 33.1C9.3 39.6 16.1 44 24 44z"/>
    <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.7 2-2 3.8-3.6 5.1l6.2 5.2c-.4.4 6-4.3 6-14.3 0-1.2-.1-2.4-.3-3.5z"/>
  </svg>
);

const SIZE_MAP = {
  small:    { pad: "px-3 py-1.5",     text: "text-xs",    icon: 14, gap: "gap-2" },
  medium: { pad: "px-4 py-2.5",     text: "text-sm",    icon: 16, gap: "gap-2.5" },
  large:    { pad: "px-5 py-3.5",     text: "text-base",  icon: 20, gap: "gap-3" },
};

export default function SignInWithGoogleButton({
  size = "medium",
  variant = "auto",
  redirectPath = "/",
  onBeforeRedirect,
  className = "",
  label = "Sign in with Google",
  fullWidth = false,
}) {
  // `useDesignVariant()` returns the variant string directly, not an object.
  const design = useDesignVariant();
  const resolvedVariant = variant === "auto"
    ? (design === "radiolife" ? "radiolife" : "legacy")
    : variant;
  const s = SIZE_MAP[size] || SIZE_MAP.medium;

  const onClick = useCallback(() => {
    onBeforeRedirect?.();
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const returnTo = redirectPath || "/";
    window.location.href =
      `${window.location.origin}/api/auth/google/login?return_to=${encodeURIComponent(returnTo)}`;
  }, [onBeforeRedirect, redirectPath]);

  const themeCls = resolvedVariant === "radiolife"
    ? ("bg-white text-slate-800 border border-slate-200 "
        + "hover:bg-slate-50 hover:border-slate-300 shadow-sm")
    : ("bg-white text-slate-900 border border-white/10 "
        + "hover:bg-slate-100");

  return (
    <button
      type="button"
      data-testid="sign-in-with-google-button"
      data-variant={resolvedVariant}
      data-size={size}
      onClick={onClick}
      className={[
        "inline-flex items-center justify-center font-medium rounded-lg",
        "transition-colors duration-150 active:scale-[0.99]",
        s.pad, s.text, s.gap,
        themeCls,
        fullWidth ? "w-full" : "",
        className,
      ].filter(Boolean).join(" ")}
    >
      <GoogleGlyph size={s.icon} />
      <span>{label}</span>
    </button>
  );
}
