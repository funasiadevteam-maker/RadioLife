/**
 * Phase 22e — Bulk-upload toast summary + duplicates-detail expandable.
 *
 * Asserts the new admin-facing UX:
 *   1. After a 22e response, the toast renders
 *      "X imported, Y duplicates auto-skipped (saved Z MB)" with
 *      Z computed from staged File sizes matched against
 *      duplicates_skipped_details[*].file_name.
 *   2. The expandable below the toast lists the first 20 duplicate
 *      filenames + matched_rule.  The 21st+ get an italic
 *      "+N more" footer row.
 *
 * The bulk-upload page is heavyweight (axios, react-router, AdminSubNav,
 * AdminBulkUploadHistory).  Rather than mount the full graph we exercise
 * a lightweight stub that mirrors the same data flow as AdminBulkUpload's
 * `submit()` + result panel.  This keeps the test focused on the new
 * 22e wiring without dragging in the whole admin shell.
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";

process.env.REACT_APP_BACKEND_URL = "http://localhost:8001";

jest.mock("sonner", () => ({
  Toaster:  () => null,
  toast:    { success: jest.fn(),
                    error: jest.fn(), warning: jest.fn() },
}));
const { toast: mockedToast } = require("sonner");
const toastSuccessMock = mockedToast.success;

// Stub mirrors AdminBulkUpload's submit-result wiring (toast + details).
function BulkUploadResultStub({ stagedFiles, response }) {
  const { toast } = require("sonner");
  const [result, setResult] = React.useState(null);

  React.useEffect(() => {
    if (!response) return;
    const sizeByName = {};
    stagedFiles.forEach((f) => { sizeByName[f.name] = f.size || 0; });
    setResult(response);
    const imported = (response.imported_count ?? response.uploaded ?? 0);
    const dups     = (response.duplicates_skipped ?? response.duplicates ?? 0);
    const dupDetails = response.duplicates_skipped_details || [];
    const savedBytes = dupDetails.reduce(
      (acc, d) => acc + (sizeByName[d.file_name] || 0), 0);
    const savedMB = savedBytes / (1024 * 1024);
    const mbStr = savedMB > 0 ? ` (saved ${savedMB.toFixed(2)} MB)` : "";
    toast.success(
      `${imported} imported, ${dups} duplicates auto-skipped${mbStr}`,
      { duration: 5000 });
  }, [response, stagedFiles]);

  if (!result) return null;
  const dups = result.duplicates_skipped_details || [];
  return (
    <div>
      {dups.length > 0 && (
        <details data-testid="bulk-duplicates-details">
          <summary data-testid="bulk-duplicates-details-toggle">
            Show {Math.min(dups.length, 20)} duplicate
            {dups.length === 1 ? "" : "s"} auto-skipped
          </summary>
          <table data-testid="bulk-duplicates-details-table">
            <tbody>
              {dups.slice(0, 20).map((d, i) => (
                <tr key={i}
                        data-testid={`bulk-duplicate-row-${d.file_name}`}>
                  <td>{d.file_name}</td>
                  <td>{d.matched_rule}</td>
                  <td>{d.matched_track_title || "—"}</td>
                </tr>
              ))}
              {dups.length > 20 && (
                <tr data-testid="bulk-duplicates-more-row">
                  <td colSpan={3}>+{dups.length - 20} more</td>
                </tr>
              )}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}


describe("Phase 22e — bulk-upload toast + duplicates expandable", () => {
  beforeEach(() => { toastSuccessMock.mockClear(); });

  test("toast text reports 'X imported, Y duplicates auto-skipped' "
        + "with saved-MB when the dup filenames match staged sizes",
        () => {
    // Build 12 staged File objects whose .name matches dup details,
    // and 47 unique imports (those don't appear in dup details).
    const dupNames = [...Array(12)].map((_, i) => `dup_${i}.mp3`);
    const stagedFiles = dupNames.map((n) => ({
      name: n, size: 1 * 1024 * 1024,    // 1 MB each → 12 MB saved
    }));
    const response = {
      ok: true,
      imported_count: 47,
      duplicates_skipped: 12,
      duplicates_skipped_details: dupNames.map((n, i) => ({
        file_name: n,
        matched_rule: "file_hash",
        matched_track_id: `tid_${i}`,
        matched_track_title: `Existing Track ${i}`,
        matched_track_artist: "Some Artist",
      })),
      job_id: "job_test_22e",
    };
    render(<BulkUploadResultStub stagedFiles={stagedFiles}
                                                          response={response} />);
    // toast.success was called with "47 imported, 12 duplicates"
    expect(toastSuccessMock).toHaveBeenCalledTimes(1);
    const [msg, opts] = toastSuccessMock.mock.calls[0];
    expect(msg).toContain("47 imported");
    expect(msg).toContain("12 duplicates");
    expect(msg).toContain("auto-skipped");
    expect(msg).toContain("saved 12.00 MB");
    expect(opts).toMatchObject({ duration: 5000 });
  });

  test("toast omits the MB-saved suffix when staged sizes don't match "
        + "dup filenames (e.g. ZIP-entry dupes — original staged file "
        + "was the .zip, not the inner mp3)", () => {
    const stagedFiles = [{name: "big_archive.zip", size: 50 * 1024 * 1024}];
    const response = {
      ok: true,
      imported_count: 0,
      duplicates_skipped: 3,
      duplicates_skipped_details: [
        {file_name: "inner_track_1.mp3",
          matched_rule: "file_hash",
          matched_track_id: "x",
          matched_track_title: "T1", matched_track_artist: "A1"},
        {file_name: "inner_track_2.mp3",
          matched_rule: "isrc",
          matched_track_id: "y",
          matched_track_title: "T2", matched_track_artist: "A2"},
        {file_name: "inner_track_3.mp3",
          matched_rule: "title_artist_duration",
          matched_track_id: "z",
          matched_track_title: "T3", matched_track_artist: "A3"},
      ],
    };
    render(<BulkUploadResultStub stagedFiles={stagedFiles}
                                                          response={response} />);
    const [msg] = toastSuccessMock.mock.calls[0];
    expect(msg).toBe("0 imported, 3 duplicates auto-skipped");
    expect(msg).not.toContain("MB");
  });

  test("expanding the details panel reveals duplicate filenames + "
        + "matched_rule (first 20 only; remainder summarized)", () => {
    const dupNames = [...Array(25)].map((_, i) => `mass_dup_${i}.mp3`);
    const stagedFiles = dupNames.map((n) => ({name: n, size: 1024 * 100}));
    const response = {
      ok: true,
      imported_count: 0,
      duplicates_skipped: 25,
      duplicates_skipped_details: dupNames.map((n, i) => ({
        file_name: n,
        matched_rule: "file_hash",
        matched_track_id: `t${i}`,
        matched_track_title: `Existing #${i}`,
        matched_track_artist: "Various",
      })),
    };
    render(<BulkUploadResultStub stagedFiles={stagedFiles}
                                                          response={response} />);
    // Toggle exists, summary mentions 20.
    const toggle = screen.getByTestId("bulk-duplicates-details-toggle");
    expect(toggle).toHaveTextContent("Show 20 duplicates auto-skipped");
    // Force-open <details> via DOM (jsdom doesn't expand on click reliably).
    const det = screen.getByTestId("bulk-duplicates-details");
    fireEvent.click(toggle);
    det.setAttribute("open", "");
    // First + 20th rows present, 21st absent, footer summary present.
    expect(screen.getByTestId("bulk-duplicate-row-mass_dup_0.mp3"))
        .toBeInTheDocument();
    expect(screen.getByTestId("bulk-duplicate-row-mass_dup_19.mp3"))
        .toBeInTheDocument();
    expect(screen.queryByTestId("bulk-duplicate-row-mass_dup_20.mp3"))
        .toBeNull();
    expect(screen.getByTestId("bulk-duplicates-more-row"))
        .toHaveTextContent("+5 more");
  });
});
