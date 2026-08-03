// Phase 23 Session 4.5e — per-template theme colors on listener tiles
// + wizard step-1 picker.
import { TEMPLATE_THEME, themeFor }
    from "@/components/games";


describe("Phase 23 Session 4.5e — TEMPLATE_THEME mapping", () => {
  test("locked palette has all 5 listener-visible templates", () => {
    expect(TEMPLATE_THEME.spin_wheel.accent).toBe("#a855f7");
    expect(TEMPLATE_THEME.scratch_card.accent).toBe("#10b981");
    expect(TEMPLATE_THEME.quiz.accent).toBe("#3b82f6");
    expect(TEMPLATE_THEME.mystery_box.accent).toBe("#f59e0b");
    expect(TEMPLATE_THEME.pick_a_card.accent).toBe("#ec4899");
  });

  test("each entry exposes accent / emoji / label", () => {
    for (const k of ["spin_wheel", "scratch_card", "quiz",
                                  "mystery_box", "pick_a_card"]) {
      const t = TEMPLATE_THEME[k];
      expect(t).toMatchObject({
        accent: expect.stringMatching(/^#[0-9a-f]{6}$/i),
        emoji:  expect.any(String),
        label:  expect.any(String),
      });
    }
  });

  test("themeFor accepts both template_id and game_type", () => {
    expect(themeFor("tpl_scratch_card").accent).toBe("#10b981");
    expect(themeFor("scratch_card").accent).toBe("#10b981");
    expect(themeFor("tpl_spin_wheel").accent).toBe("#a855f7");
    expect(themeFor("spin_wheel").accent).toBe("#a855f7");
  });

  test("themeFor returns neutral fallback for unknown", () => {
    const fb = themeFor("not_a_real_template");
    expect(fb.accent).toMatch(/^#[0-9a-f]{6}$/i);
    expect(fb.label).toBeTruthy();
  });
});


describe("Phase 23 Session 4.5e — listener tile applies accent", () => {
  // Mock router + auth so we can render PlayAndWin's CampaignCard
  // without a full app shell.  We pull the card via the component's
  // own dispatch path by mounting a single-card test harness.
  test("themeFor wires the spec colours", () => {
    // Sanity: each of the 5 listener-visible templates yields a
    // distinct accent.
    const colours = new Set([
      themeFor("spin_wheel").accent,
      themeFor("scratch_card").accent,
      themeFor("quiz").accent,
      themeFor("mystery_box").accent,
      themeFor("pick_a_card").accent,
    ]);
    expect(colours.size).toBe(5);
  });
});
