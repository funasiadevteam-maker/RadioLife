# RadioLife Social V2 — Master Prompt: DREAMS & GUIDANCE (New Section)

> **Status:** Spec / roadmap addition to the RadioLife Social V2 master prompt. **Not yet built.**
> **Sequencing:** Dreams & Guidance is a later phase of Social V2 (after Live Commerce, Moments, Clubs, Go Together). It is a *distinct* social experience — **not** mixed into the main Together feed — but it connects into Moments, Clubs, Advisors, Scheduling and Commerce.
> **Architecture rule (hard):** DO NOT build a separate standalone fortune-telling app. Reuse RadioLife's shared foundations — Social identity, profiles, friends, Moments, Clubs, Live, audio/video infra, merchant/service marketplace, Stripe/payments, scheduling, notifications, reviews, moderation, privacy, analytics, BigPoints, Admin and feature flags.

---

## 0. POSITIONING & THE PRODUCT LOOP
- Add a new social/community experience: **DREAMS & GUIDANCE**.
- Position as **reflection · entertainment · spiritual guidance · personal exploration** — **NOT** astrology/tarot/numerology/dream-interpretation/fortune-telling presented as scientifically proven fact.
- The social loop that makes it a community (not just AI generators):
  **share a dream → find similar dreams → comments → AI reflection → advisor opinion → optional private consultation.**
- Where licensed medical / mental-health / sleep professionals participate, their services are **clearly separated** from spiritual/entertainment services and follow applicable professional/licensing requirements.

## 1. ENTRY & IA (§120)
- New destination: **Social › Dreams & Guidance** as a featured Social experience / Club-category / secondary hub — **do not replace** the primary Social hierarchy (Together · Live · Moments · Clubs · Friends).
- Sub-tabs: **Dreams · AI Readings · Advisors · My Readings**.

## 2. DREAM SHARING (§121–§127)
- **Share a Dream:** optional Title, required Description, optional dream date, mood (Happy/Scary/Confusing/Peaceful/Sad/Exciting/Strange/Other), optional tags (Flying, Falling, Water, Animals, Family, Death, Work, Love, Travel, Religious/Spiritual, Recurring, Lucid, Nightmare, Other).
- **Share with my name** or **Share anonymously**.
- **Anonymous = anonymous to other users, NOT untraceable to RadioLife.** Backend retains `user_id`, moderation/audit ownership, report handling, abuse prevention. Public shows "Anonymous Dreamer"; never expose name/profile/email/phone/location.
- **Visibility:** Only Me · Friends · Club · Public · Anonymous Public. Sensitive dreams default to Friends/Private unless user explicitly picks Public.
- **Dream feed** card: title, preview, mood, tags, named/Anonymous, time, comments, similar-dream count, advisor responses, save, report. Actions: *I Had a Similar Dream · Comment · Ask for Interpretation · Save · Share*.
- **"I Had a Similar Dream"** = distinct action; increments similarity count (idempotent, no spam), optionally prompts "Share yours?" → creates dream clusters (e.g., "243 people had a similar dream").
- **Comments** support text, voice reply, supportive reactions (I relate / Interesting / Comforting / I've dreamed this too) and advisor replies — not Like-only.

## 3. AI DREAM TOOLS & SAFETY (§128–§131, §158)
- **Explore This Dream with AI** → framed as *possible reflection / symbolic interpretation / common cultural reading / questions to consider*. Header: *"This is one possible interpretation, not a factual diagnosis or prediction."*
- **AI must NOT:** diagnose psychiatric illness or sleep disorders; state supernatural explanations as verified fact; predict death/future events as certainty; give medical diagnosis; encourage dangerous actions. Use "Some traditions interpret…", "One possible symbolic reading…", "You may want to reflect on…" — never "This definitely means…".
- If a user asks e.g. *"Does this dream mean I have schizophrenia?"* → AI does not diagnose; explains dreams alone can't establish a diagnosis and suggests a licensed professional if the experience is distressing.
- **My Dream Journal** (private by default): save, tag recurring themes, track emotions, search, notes, AI reflection, choose later whether to share.
- **Dream Patterns:** pattern recognition only (e.g., "Water appeared in 5 dreams", "Most common mood: Anxious") — **no medical conclusions**.
- **Dream clusters:** AI groups semantically similar dreams; label as "Common Themes People Discuss" / "Possible Interpretations" — never "these dreams objectively mean X."

## 4. ADVISORS & CREDENTIAL DISTINCTION (§132–§136, §157, §171)
- Approved advisors reply to public dreams with an **identity category** shown (Verified Spiritual Advisor, Dream Interpreter, Astrologer, Tarot Reader, Numerologist, Licensed Sleep Professional, Licensed Mental Health Professional) — **no single generic "Expert" badge.**
- **Separate spiritual/entertainment advisors from licensed health professionals.** Spiritual advisors must **not** get Medical/Doctor/Therapist/Psychologist/Sleep-Specialist badges unless credentials are verified and scope supports it.
- **Distinct badges:** Identity Verified · Spiritual Advisor Approved · Professional License Verified. Never one checkmark that makes all advisors look medically credentialed.
- Licensed pros: verify credential type, jurisdiction, license number, expiry, status, allowed region, category; public dream comments stay educational/general/non-diagnostic. Real healthcare consultation, if ever enabled, uses a separate compliant telehealth workflow — a public dream thread is **not** a medical consultation.
- **Ask an Advisor** → AI Reflection · Spiritual Advisor · Dream Interpreter · Astrologer · Tarot Reader · Numerologist · Licensed Professional (where available). Free short public response → *"Want a deeper reading?"* → **Request Private Reading**.

## 5. PAID READINGS & MARKETPLACE (§137–§144, §193 reuse)
- **Detailed Private Reading** delivery: Written · Voice · Recorded Video · Live Video · Live Audio. Advisor configures price, duration, delivery time, description, availability.
- **Booking reuses existing RadioLife identity, payments, merchant/service architecture and calendar/scheduling.** Select advisor/service/date/time/price/timezone → Book. **No separate payment system.**
- **Async reading** (e.g., "30-min Written Dream Reading — $29, delivery within 24h"): user submits dream + optional questions/voice note; advisor delivers private response.
- **Live private reading** (30/45/60 min, audio or video) uses RadioLife Live infra; **private consultations never appear in the public Live feed.**
- **Advisor Marketplace ("Find an Advisor"):** categories (Dream Interpretation, Astrology, Tarot, Cartomancy, Numerology, Spiritual Guidance, Meditation, Sleep Education, Mental Health Professional where enabled); filters (language, price, rating, availability, format, verified, specialty). Advisor profile: photo, name, category, verification badge, bio, languages, experience, credentials, services, pricing, availability, reviews, public answers, live events, videos/Moments; buttons Ask a Question / Book Private Reading / Follow / View Services.
- **Business model:** advisors are service providers — reuse merchant/service onboarding, **Stripe Connect, payouts, commission engine, reviews, scheduling, verification.** Admin controls platform fee, payout, refund/cancellation rules, tax, promos. **Do not hardcode commission.**
- **Advisor advertising:** Sponsored Advisor / Sponsored Live / Featured Reading / Promoted Moment — always labeled **SPONSORED/PROMOTED**. Payment must **never** secretly influence reviews, verification, medical badges or organic ratings.

## 6. AI SPIRITUAL EXPERIENCES (§145–§153)
- **AI Horoscope** (labeled AI-GENERATED, for entertainment/reflection): inputs DOB, optional birth time/place, timezone; outputs daily/weekly/monthly/birth-chart/relationship/career/themes — never a guaranteed prediction.
- **Match Horoscopes** (Romantic/Friendship/Business/Family): compatibility themes, strengths, tensions, reflection questions — no "Guaranteed Match", "Soulmate Probability", "Divorce Risk".
- **Private data (§147):** birth info is sensitive — allow save / don't save / delete; never expose birth time/location publicly by default; encourage consent before saving another person's data.
- **AI Tarot** (General/Love/Career/Decision/Past-Present-Future/Custom; 1/3/configurable spreads; upright/reversed; traditional symbolism + AI reflection) with disclaimer.
- **Cartomancy** (traditional playing-card interpretation) and **Numerology** (Life Path, Birthday, Expression/Destiny, Soul Urge, Personal Year, compatibility) — **show the calculation methodology; don't hide it behind AI.**
- **Fortune & Reflection** hub groups Astrology/Tarot/Cartomancy/Numerology/Dream Reflection — guidance/reflection/entertainment, never "AI predicts exactly what will happen to you."
- **Share Reading** as a Moment (e.g., "My Tarot Card Today") with privacy controls; never auto-share birth info or the private question.
- **Compare with a Friend (§154):** friend must **Accept** before saved profile data is used; alternative = manual temporary entry without saving.

## 7. COMMUNITIES & LIVE (§155–§156, §181)
- **Dream/Spiritual Clubs** (Dream Journal Club, Lucid Dreamers, Recurring Dreams, Nightmare Support, Astrology Lovers, Tarot Community, Numerology) reuse existing Club privacy/moderation.
- **Live advisor events** (Dream Q&A, Tarot Live, Astrology Q&A, Numerology Workshop, Meditation, Sleep Education) on RadioLife Live; clearly show host type (spiritual advisor / entertainment reader / licensed professional). Advisors may pin approved consultation/workshop/reading products — **no fear-based upsell.**

## 8. SAFETY, ETHICS & FRAUD (§157–§164, §174)
- **No false medical authority:** reject/remove medical claims from unlicensed spiritual providers (e.g., "this card shows you have cancer", "your horoscope means stop your medication").
- **High-risk decision boundary:** readings must not drive medical treatment, large financial moves, legal action, self-harm or dangerous activity; show safety messaging.
- **Advisor Code of Conduct:** no guaranteed predictions/healing/supernatural certainty; no diagnosis unless properly licensed; no coercion; no "you're cursed unless you pay"; no repeat-purchase pressure; no manipulating vulnerable users; no prohibited off-platform payment.
- **Fraud/exploitation detection + Admin moderation queue:** curse-removal extortion, guaranteed lottery/investment/pregnancy predictions, certainty death predictions, unlicensed diagnosis, payment pressure, romance manipulation, vulnerable-user upsell.
- **Age policy:** paid spiritual/fortune services **18+ by default** (regionally configurable); never target fortune-telling ads to minors.
- **Advertising controls:** never target users off distressing dream content / mental-health implications / grief / medical inferences (e.g., a death-dream must not trigger "talk to a psychic about death" ads).
- **Ratings/reviews:** rate communication/professionalism/helpfulness/value — **never "prediction accuracy."** Distinguish verified paid appointment vs public interaction.
- **Refunds/disputes:** configurable (no-show, technical failure, non-delivery, duplicate charge); do **not** promise refunds because a prediction didn't happen or the user disliked an interpretation, unless policy says so.

## 9. DISCLAIMERS & LIABILITY (§165–§169) — *includes the requested wording change*
- **Global disclaimer** on every AI horoscope / tarot / numerology / cartomancy / fortune / dream interpretation:
  > *"RadioLife's spiritual, astrology, tarot, numerology and dream features are provided for entertainment, reflection and general informational purposes. They are not medical, mental-health, legal or financial advice and no result or prediction is guaranteed."*
- **Advisor booking disclaimer** (accept "I Understand" before first paid spiritual consultation):
  > *"Advisor opinions and interpretations are the advisor's own. RadioLife does not guarantee the accuracy, outcome or predictive value of spiritual, astrology, tarot, numerology or dream-reading services."*
- **Licensed professionals:** separate professional consent appropriate to the service; display professional type, verified credential, jurisdiction, scope — **do not** cover them under the spiritual disclaimer alone.
- **⚠️ LIABILITY — corrected stance (do NOT use a blanket "RadioLife has no liability" notice):** In-app UI must clearly explain that services are **interpretive**, results are **not guaranteed**, they are **not professional medical/legal/financial advice**, and users remain responsible for their own decisions. The **actual limitation-of-liability language belongs in the Terms of Service / Advisor Terms / Marketplace Terms, drafted or approved by legal counsel, and jurisdiction-configurable.** A standalone "no liability" sentence is **not** something to rely on.
- **Consent before first AI reading (§169):** "Welcome to Dreams & Guidance" + checkbox acknowledging AI/spiritual readings are entertainment/reflection and not guaranteed/professional advice; store `terms_version` + `accepted_at`; don't re-prompt every session unless terms materially change.

## 10. ADVISOR ONBOARDING & VERIFICATION (§170–§172)
- Application fields: name, profile, category, languages, experience, services, pricing, availability, identity verification, professional credentials (if applicable), tax/payment info, terms acceptance. Status: Applied → Under Review → Approved → Rejected → Suspended.
- Verification badges kept distinct (Identity Verified / Spiritual Advisor Approved / Professional License Verified).
- **Private messaging:** no unsolicited advisor DMs — users initiate via question/booking/consultation; advisors communicate within booking/service/existing conversation.

## 11. USER CONTROLS, PERSONALIZATION & BIGPOINTS (§173, §175, §182)
- Users can: block advisor, hide category, report reading, delete dream, make anonymous, change privacy, delete reading history, disable spiritual recommendations.
- AI personalizes **only** on explicitly selected interests, retained readings, saved dream tags, preferred traditions, language — **never infer religion or medical condition from dream text for ad targeting.**
- **BigPoints** only via configured rewards (event attendance, community participation, booking promos, campaigns). **Never** reward publicly sharing sensitive dreams, revealing trauma, or buying repeated fortune readings. Do not optimize for vulnerable-user repeat spending.

## 12. ADMIN, FLAGS, SEARCH, ANALYTICS, DESIGN (§176–§185, §189)
- **Admin › Dreams & Guidance:** Dream Moderation, Advisor Applications, Advisor Verification, Professional Credentials, Services, Bookings, Disputes, AI Reading Configuration, Content Policies, Disclaimers, Pricing/Commission, Sponsored Advisors, Reports, Safety Review.
- **Admin AI config:** enable/disable Dream AI, Astrology, Compatibility, Tarot, Cartomancy, Numerology, Advisor Marketplace, Paid Consultations, Licensed Professional Services — by region/age/pilot cohort/flag.
- **Admin content config:** tarot decks, allowed spreads, astrology & numerology methodology, dream-AI prompt policy, disclaimer text, terms versions, max advisor prices, service categories, durations.
- **Feature flags:** `dream_sharing_enabled`, `dream_ai_enabled`, `astrology_enabled`, `tarot_enabled`, `cartomancy_enabled`, `numerology_enabled`, `advisor_marketplace_enabled`, `paid_readings_enabled`, `licensed_professional_services_enabled` (behind region/age/role/pilot).
- **Search:** Dream Topics, Advisors, Astrology, Tarot, Numerology, Clubs, Live Sessions.
- **Analytics:** dreams_created, anonymous_dream_share_rate, dream_comments, similar_dream_actions, AI reflections, advisor public responses, advisor profile views, reading requests, booking conversion, consultations completed, live advisor viewers, repeat bookings, reports, refunds, advisor moderation rate. **Do not optimize for vulnerable-user repeat spending.**
- **Design (New Look V2 primary):** premium dark/reflective — Dreams: deep navy/violet, subtle stars/abstract textures (NOT cheap "psychic neon"); Tarot: elegant cards; Astrology: premium celestial visuals; Advisor marketplace: professional marketplace design. Compatible with legacy/radiolife/classic_b; business logic shared.
- **Social Home & Moments integration (§179–§180):** surface Dream trending topics / Advisor Live / friend-shared dreams sparingly (don't overwhelm Together/Live/Moments/Clubs/Friends); allow Dream/Horoscope/Tarot/Numerology Moments + Advisor clips with **privacy-by-default** for personal data.
- **Respectful upsell (§188):** after an AI reading → "Want a human perspective? [View Advisors]" — never "This reading shows danger — pay $49 to learn more." Never use fear to drive purchase.

## 13. DATA MODEL (reuse-first)
- Reuse Social V2 models (SocialProfile, Moments, Clubs, Live, Plans, Reviews) + marketplace/service-provider + payments + scheduling.
- New where absent: `Dream`, `DreamTag`, `DreamSimilarity`, `DreamComment`, `DreamVoiceReply`, `DreamCluster`, `DreamJournalEntry`, `AIReading` (type: horoscope|tarot|cartomancy|numerology|dream_reflection), `AdvisorProfile` (extends service-provider), `AdvisorService`, `ReadingBooking` (extends existing booking/payment), `AdvisorReview`, `SpiritualConsentRecord`, `GuidanceFeatureFlag`.

## 14. ACCEPTANCE TESTS (§190–§197)
- **Anonymous dream:** public shows "Anonymous Dreamer"; identity not retrievable via public API; Admin can identify owner. ✅
- **Similar dream:** idempotent increment; no repeat-spam of same dream. ✅
- **AI dream:** reflective, no certainty, no diagnosis, disclaimer shown. ✅
- **Paid advisor:** booking uses existing marketplace/payments; advisor receives booking; commission/payout per config. ✅
- **License badge:** spiritual advisor without medical credential cannot show "Licensed Medical Professional." ✅
- **Advisor abuse:** "You are cursed and must pay $500 now" → high-priority moderation flag. ✅
- **High-stakes AI:** "Should I stop my medication?" → tarot must not decide; redirect to licensed medical guidance. ✅
- **Privacy:** private Journal entry never appears in Social; birth details excluded from a shared horoscope Moment unless explicitly selected. ✅

## 15. FINAL POSITIONING (§198–§199)
- Dreams & Guidance should feel like **a community for reflection**: share a dream (named or anonymous) → discover similar dreamers → discuss → AI reflection → approved-advisor input → optional private reading; plus explore astrology, compare horoscopes, try tarot/cartomancy/numerology, and join live sessions.
- RadioLife stays clear: interpretations are not guaranteed facts; readings are not medical/legal/financial advice; AI readings are AI-generated; licensed professionals are separately identified & verified; users retain responsibility for decisions.
- **It is another differentiated RadioLife social community, not a disconnected app** — reusing identity, friends, Moments, Clubs, Live, media infra, marketplace, payments, scheduling, notifications, reviews, moderation, privacy, analytics, BigPoints, Admin and feature flags.
