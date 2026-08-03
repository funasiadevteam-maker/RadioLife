// Phase 15a — dev-only styleguide. Mounted at /dev/styleguide (excluded
// from the app shell by BARE_ROUTES regex).
import React from "react";
import {
  Card, Button, Chip, LiveDot, StationTile, GameTile,
  WalletItemCard, MiniPlayer,
} from "./primitives";

const TOKENS = [
  { name: "--bg-base",         hex: "#0A0A0F", swatch: "bg-bg-base" },
  { name: "--bg-elevated",     hex: "#14141C", swatch: "bg-bg-elevated" },
  { name: "--bg-glass",        hex: "rgba(255,255,255,0.04)",
                                          swatch: "bg-bg-glass backdrop-blur-glass" },
  { name: "--accent-electric", hex: "#00D4FF",
                                          swatch: "bg-accent-electric" },
  { name: "--accent-magenta",  hex: "#FF2E8E",
                                          swatch: "bg-accent-magenta" },
  { name: "--accent-gold",     hex: "#FFB400", swatch: "bg-accent-gold" },
  { name: "--accent-success",  hex: "#00E08A",
                                          swatch: "bg-accent-success" },
  { name: "--accent-live",     hex: "#FF3B30", swatch: "bg-accent-live" },
];

export default function Styleguide() {
  return (
    <div data-testid="styleguide-root"
            className="min-h-screen bg-bg-base text-text-primary font-sans
                            px-8 py-10">
      <div className="max-w-6xl mx-auto space-y-12">
        <header className="space-y-2">
          <div className="text-[10px] font-mono uppercase tracking-widest
                                text-text-secondary">
            phase 15a · dev only
          </div>
          <h1 className="font-display font-bold text-4xl tracking-display-tight">
            BigFM.AI <span className="text-accent-electric">styleguide</span>
          </h1>
          <p className="text-text-secondary text-sm max-w-xl">
            Lock-in for tokens + primitives. Edit the values in
            <code className="mx-1 font-mono text-accent-electric">
              tailwind.config.js
            </code>
            and
            <code className="mx-1 font-mono text-accent-electric">
              src/index.css
            </code>
            — everything below updates.
          </p>
        </header>

        <section>
          <h2 className="font-display font-bold text-xl mb-4">Tokens</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4
                                gap-3">
            {TOKENS.map((t) => (
              <Card key={t.name} className="p-3">
                <div className={`${t.swatch} h-14 rounded-token-md border
                                          border-white/[0.06]`} />
                <div className="mt-2 font-mono text-[11px]">{t.name}</div>
                <div className="font-mono text-[10px] text-text-secondary">
                  {t.hex}
                </div>
              </Card>
            ))}
          </div>
        </section>

        <section>
          <h2 className="font-display font-bold text-xl mb-4">Typography</h2>
          <div className="space-y-4">
            <Card className="p-5">
              <div className="text-[10px] font-mono uppercase text-text-secondary
                                    mb-1">Display · Space Grotesk 700</div>
              <div className="font-display font-bold text-4xl
                                    tracking-display-tight">
                The pulse of your city, on air.
              </div>
            </Card>
            <Card className="p-5">
              <div className="text-[10px] font-mono uppercase text-text-secondary
                                    mb-1">Body · Inter 500</div>
              <div className="font-sans font-medium text-base">
                Tune in to Lunch Rush — Bollywood + EDM mashups until 2 PM.
                Win a free karak at Lulu (Dubai Marina).
              </div>
            </Card>
            <Card className="p-5">
              <div className="text-[10px] font-mono uppercase text-text-secondary
                                    mb-1">Mono · JetBrains Mono 400</div>
              <div className="font-mono text-sm">
                JOIN-CODE · K7-XQ-92 · expires in 04:21
              </div>
            </Card>
          </div>
        </section>

        <section>
          <h2 className="font-display font-bold text-xl mb-4">Buttons</h2>
          <div className="flex flex-wrap gap-3 items-center">
            <Button>Primary</Button>
            <Button variant="magenta">Play & Win</Button>
            <Button variant="gold">Claim reward</Button>
            <Button variant="outline">Try the demo</Button>
            <Button variant="ghost">Skip</Button>
            <Button variant="danger">End live</Button>
            <Button size="sm">Small</Button>
            <Button size="lg">Large</Button>
          </div>
        </section>

        <section>
          <h2 className="font-display font-bold text-xl mb-4">Chips</h2>
          <div className="flex flex-wrap gap-2">
            <Chip>All</Chip>
            <Chip active>Bollywood</Chip>
            <Chip tone="live"><LiveDot /> Live</Chip>
            <Chip tone="electric">Now playing</Chip>
            <Chip tone="gold">Rewards</Chip>
          </div>
        </section>

        <section>
          <h2 className="font-display font-bold text-xl mb-4">Tiles</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StationTile name="Bollywood Mehfil" dj="DJ Ananya"
                              onPlay={() => {}} live />
            <StationTile name="Hip-hop Late" dj="DJ Karan"
                              onPlay={() => {}} />
            <GameTile name="Karak Quiz" prize="Free karak ×3"
                          onJoin={() => {}} />
            <WalletItemCard title="Lulu coupon — AED 10 off"
                                      expires="Expires Fri" badge="NEW" />
          </div>
        </section>

        <section>
          <h2 className="font-display font-bold text-xl mb-4">
            Mini-player (glass)
          </h2>
          <div className="max-w-md">
            <MiniPlayer />
          </div>
        </section>

        <section>
          <h2 className="font-display font-bold text-xl mb-4">
            Breakpoints
          </h2>
          <Card className="p-5 font-mono text-xs space-y-1">
            <div>sm  ≥ 640</div>
            <div>md  ≥ 768  · TabletShell mounts</div>
            <div>lg  ≥ 1024 · DesktopShell mounts (sidebar + bottom player)</div>
            <div>xl  ≥ 1280</div>
            <div>2xl ≥ 1536</div>
          </Card>
        </section>

        <section>
          <h2 className="font-display font-bold text-xl mb-4">
            Keyboard shortcuts (desktop)
          </h2>
          <Card className="p-5 font-mono text-xs grid grid-cols-2 gap-2">
            <div>space · play / pause</div>
            <div>← / → · volume down / up</div>
            <div>/ · focus search</div>
            <div>j / k · next / prev in list</div>
            <div>g h · home</div>
            <div>g r · radio</div>
            <div>g p · play &amp; win</div>
            <div>g t · trivia</div>
            <div>g w · wallet</div>
            <div>g g · passport</div>
          </Card>
        </section>
      </div>
    </div>
  );
}
