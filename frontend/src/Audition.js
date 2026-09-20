// /audition — Phase 3.6 public, NO-AUTH audition page.
// Hits the public `/api/audition/<key>/audio` MP3 routes. Mirrors the SSR
// HTML rendered by routes/audition.py so the user gets the same experience
// whether they land via the React shell or directly on /api/audition/__landing.

import { useMemo } from "react";
import { Link } from "react-router-dom";

const API = process.env.REACT_APP_BACKEND_URL || "";
const BACKEND = API.replace(/\/$/, "");

const SAMPLES = [
  // ---------- Phase 3.8 v2 — Station Imaging Engine LIVE showcase ----------
  {
    key: "phase38_morning_imaging",
    title: "Morning Drive · Imaging LIVE",
    voice_meta: "Phase 3.8 v2 · brand_id_short pre-roll + music bed under RJ + -14 LUFS",
    channel: "bollywood_mehfil", hosts: ["Aanya"], format: "solo",
    excerpt: "Morning Drive opener — 2.9s station ID pre-roll, bed_medium running under the RJ break, fully loudness-normalized.",
  },
  {
    key: "phase38_nightlife_imaging",
    title: "DUO · Sponsor + sweeper + bed",
    voice_meta: "Phase 3.8 v2 · DUO 2-stage rewrite + sponsor_bumper + sweeper + music bed",
    channel: "bollywood_mehfil", hosts: ["Charlie", "Aanya"], format: "duo",
    excerpt: "Full produced break — sponsor lead-in, sweeper transition, two-host banter over a music bed.",
  },
  {
    key: "phase38_late_night_chill",
    title: "Late Night Chill · Bed-only LIVE",
    voice_meta: "Phase 3.8 v2 · music bed under RJ, no pre-roll (in-cadence segment)",
    channel: "bollywood_mehfil", hosts: ["Veer"], format: "solo",
    excerpt: "Mid-cadence segment with bed running underneath — the polish you only notice when it's gone.",
  },
  // ---------- Phase 3.7 — Personality profile showcase ----------
  {
    key: "phase37_morning_drive",
    title: "Morning Drive · Aanya (Hindi-native)",
    voice_meta: "ElevenLabs eleven_v3 · Aanya · profile=morning_drive · two-stage pipeline",
    channel: "morning_masala", hosts: ["Aanya"], format: "solo",
    excerpt: "Dubai, good morning! 4:00 AM ho chuki hai, aur morning ride ka scene set hai yahan Morning Masala, FUUSIC par! [smiles] Kaise ho guys? Weekend ka mood kaisa chal raha hai? Bahar thandi hawa hai, aur traffic jams bhi shuru hone wale hain!",
  },
  {
    key: "phase37_lunch",
    title: "Lunch Rush · Veer (Hinglish smooth)",
    voice_meta: "ElevenLabs eleven_v3 · Veer · profile=lunch · two-stage pipeline",
    channel: "late_night_drive", hosts: ["Veer"], format: "solo",
    excerpt: "[gently] Kya scene hai, doston! Aaj raat thoda chill karne ka time hai... jab chand chamakta hai aur khwabon ka safar shuru hota hai. [pause] Thodi der ke liye, hum iss kahani mein kho jaate hain.",
  },
  {
    key: "phase37_evening_drive",
    title: "Evening Drive · Raghav (Hindi-native)",
    voice_meta: "ElevenLabs eleven_v3 · Raghav · profile=evening_drive · two-stage pipeline",
    channel: "bollywood_mehfil", hosts: ["Raghav"], format: "solo",
    excerpt: "Kya haal hai dosto? [smiles] Raat ka 4 baje ka waqt hai, aur aaj thoda pyaar bhare lamhe churaane wale hain. [pause] Ab vibe ko thoda aur upar le jaate hain — ek khubsurat kahani aapko dil tak le jaayegi.",
  },
  {
    key: "phase37_nightlife",
    title: "Nightlife · DJ Charlie (OpenAI 'ash')",
    voice_meta: "OpenAI gpt-4o-mini-tts · 'ash' · profile=nightlife · two-stage pipeline",
    channel: "party_dubai", hosts: ["DJ Charlie"], format: "solo",
    excerpt: "Kya scene hai, Dubai! [smiles] Party Dubai ki vibe set hai. Samundar ki lehron ki tarah, raat ko thoda magical color chadhne wala hai! Party mood abhi bhi full on hai! [pause] Ab vibe ko thoda aur upar le jaate hain.",
  },
  {
    key: "phase37_chill_late_night",
    title: "Chill Late Night · Veer (intimate)",
    voice_meta: "ElevenLabs eleven_v3 · Veer · profile=chill_late_night · two-stage pipeline",
    channel: "late_night_drive", hosts: ["Veer"], format: "solo",
    excerpt: "[softly] Kya scene hai dosto! Late Night Drive pe aapka swagat hai FUUSIC par. [pause] Is suhani raat mein sab kuch thoda aur romantic hai. Aapki khushiyan aur khwab hi toh maayne rakhte hain. Toh relax ho jaao…",
  },
  {
    key: "phase37_talk_news",
    title: "Talk / Retro · Kishore Da (broadcaster)",
    voice_meta: "ElevenLabs eleven_v3 · Kishore Da · profile=talk_news · two-stage pipeline",
    channel: "retro_lounge", hosts: ["Kishore Da"], format: "solo",
    excerpt: "[warmly] Shubh raat, Dubai! Retro Lounge ka time hai... [pause] Raat thodi gehri ho rahi hai, aur thoda narmi zaroori hai. Aaj hum sunne wale hain ek khaas mehfil — pyaar aur yaadon se bhari.",
  },
  // ---------- Phase 3.6 — Multi-provider voice showcase ----------
  {
    key: "party_charlie_solo_1",
    title: "Party Dubai · DJ Charlie · solo open",
    voice_meta: "OpenAI gpt-4o-mini-tts · voice 'ash' · American club DJ",
    channel: "party_dubai", hosts: ["DJ Charlie"], format: "solo",
    excerpt: "Yo, yo, yo! What's up, Dubai?! It's your boy DJ Richard on FUUSIC's PARTY channel, and we're about to TURN IT UP tonight!! Whether you're cruising down Sheikh Zayed or vibing at the JBR beach club, the PARTY is just getting started, yaar!!",
  },
  {
    key: "party_charlie_solo_2",
    title: "Party Dubai · DJ Charlie · Karama after-party",
    voice_meta: "OpenAI gpt-4o-mini-tts · voice 'ash' · American club DJ",
    channel: "party_dubai", hosts: ["DJ Charlie"], format: "solo",
    excerpt: "Yo, what's up, Dubai! It's your boy DJ Richard, bringing you that late-night PARTY energy! Are you READY to turn it UP?! Karama after-party is calling, and you're gonna want to bring the FIRE! Hands in the AIR — this next beat is gonna take you to the MAX!!",
  },
  {
    key: "party_charlie_riya_duo",
    title: "Party Dubai · Charlie × Riya · DUO rapid-fire",
    voice_meta: "OpenAI gpt-4o-mini-tts · 'ash' + 'nova' · 6-turn Mirchi ping-pong",
    channel: "party_dubai", hosts: ["DJ Charlie", "DJ Riya"], format: "duo",
    excerpt: "[CHARLIE] Yaar, Riya, what a MAST night, doston!! [RIYA] Absolutely, Charlie! Dance floor is BLAZING!! [CHARLIE] This crowd is just AMAZING, doston!! [RIYA] And the energy? It's through the ROOF!! [CHARLIE] Are you READY for the next DROP, boss?? [RIYA] Let's GOOO! FUUSIC NONSTOP!!",
  },
  {
    key: "bollywood_raghav_aanya_duo",
    title: "Bollywood Mehfil · Raghav × Aanya · pure Hindi duo",
    voice_meta: "ElevenLabs eleven_v3 · native Hindi voices (Armaan + Tripti)",
    channel: "bollywood_mehfil", hosts: ["Raghav", "Aanya"], format: "duo",
    excerpt: "[RAGHAV] Kya scene hai, Aanya? Pichhle gaane ne toh dil jeet liya! [AANYA] Bilkul! Woh romantic vibe hai na, Dubai ki raat ko aur bhi khaas banata hai! [RAGHAV] Haan, aur yeh gaana bhi mast hone wala hai, dil ko chhoo lega! [AANYA] Sun lo yaar, pyaar ki baatein karte hue toh mazaa hi alag hai!",
  },
];

export default function Audition() {
  const samples = useMemo(() => SAMPLES.map((s) => ({
    ...s, audioUrl: `${BACKEND}/api/audition/${s.key}/audio`,
  })), []);

  return (
    <div className="audition-shell" data-testid="audition-page">
      <main className="audition-main">
        <header className="audition-head" data-testid="audition-header">
          <div className="brand mono">FUUSIC · Voice Audition</div>
          <h1>Phase 3.6 — <span className="accent">multi-provider voices</span></h1>
          <p className="lede">
            Four fresh samples comparing OpenAI{" "}
            <code>gpt-4o-mini-tts</code> (American DJs) with ElevenLabs{" "}
            <code>eleven_v3</code> (native Hindi). Hit play — no login needed.
          </p>
        </header>

        {samples.map((s) => (
          <section className="sample" id={s.key} key={s.key} data-testid={`audition-sample-${s.key}`}>
            <header>
              <h2>{s.title}</h2>
              <div className="meta">
                <span className="pill pill-channel mono">{s.channel}</span>
                <span className={`pill pill-${s.format} mono`}>{s.format.toUpperCase()}</span>
                <span className="hosts">{s.hosts.join(" × ")}</span>
              </div>
              <div className="voice-meta">{s.voice_meta}</div>
            </header>
            <audio
              controls
              preload="none"
              data-testid={`audition-audio-${s.key}`}
              src={s.audioUrl}
            >
              <source src={s.audioUrl} type="audio/mpeg" />
              Your browser doesn&apos;t support HTML5 audio.
            </audio>
            <details className="script">
              <summary className="mono">Script excerpt</summary>
              <p>{s.excerpt}</p>
            </details>
            <div className="actions">
              <a
                className="btn btn-secondary mono"
                href={s.audioUrl}
                download={`${s.key}.mp3`}
                data-testid={`audition-download-${s.key}`}
              >
                ↓ Download MP3
              </a>
              <a
                className="btn btn-link mono"
                href={s.audioUrl}
                target="_blank"
                rel="noopener noreferrer"
                data-testid={`audition-open-${s.key}`}
              >
                Open in new tab ↗
              </a>
            </div>
          </section>
        ))}

        <footer className="audition-foot mono">
          <span>FUUSIC · Phase 3.6</span>
          <Link to="/" data-testid="audition-back-link">← Back to radio</Link>
        </footer>
      </main>
    </div>
  );
}
