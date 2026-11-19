# Visual check

The 36 states of `docs/screenshots/` were captured from the real application with Playwright
(`frontend/scripts/capture.mjs`, same names, same viewports: 1440 px wide on desktop, 390×844 at 2× on
phone) into `docs/screenshots-build/`, then compared side by side with the reference.

**Expected differences everywhere** (not design changes):
- **Fonts:** the reference screenshots used a fallback font; the app loads Bricolage Grotesque, Geist and Geist Mono.
- **Live data:** readings, times, the clock, the greeting ("Good evening") and percentages come from the running
  simulator and the trained model, so the numbers differ from the prototype's fixed values. For example, the model gives the trout
  basin a risk close to 100 %, because it dips under its warning level almost every night (see `ml/README.md`).
- **Animations:** captures use reduced motion, like the reference (resting state).

Intended additions, required by the specifications and logged in `docs/DECISIONS.md`:
- **AI Ops** as a sixth item of the owner menu (owner-only page from CHATBOT_UPGRADE §8).
- **+ Add basin** button on the Basins page, and the **Explain this estimate** button on the prediction tile.
- In the assistant panel: a **PDF** export button, a **microphone** button where the browser supports voice input,
  and a **Recent conversations** list in the empty state when there is history.

| # | Screen | Result | Note |
|---|---|---|---|
| 01 | Website, full page | ✅ | All sections, canvas scenes and footer logo match. |
| 02 | Website hero | ✅ | Live chips show the demo farm's real readings. |
| 03 | Owner sign in | ✅ | |
| 04 | Wrong password | ✅ | Same message and position. |
| 05 | Create farm validation | ✅ | Same errors. The hint under the button now says the farm starts empty (real behaviour). |
| 06 | Team sign in | ✅ | |
| 10 | Owner overview | ✅ | Actions and summary are computed by the briefing service. |
| 11 | Basins | ✅ | Plus the "+ Add basin" button. |
| 12 | Basin detail, oxygen | ✅ | Chart, overnight-low marker and gauges match; prediction from the model. |
| 13 | Basin detail, temperature | ✅ | |
| 14 | Alerts, open | ✅ | Same three alerts, raised by the SQL alert engine and the sensor-health job. |
| 15 | Resolve dialog | ✅ | |
| 16 | Just resolved | ✅ | Green row with pop, title not struck, then moves to Done. |
| 17 | Done tab | ✅ | "Resolved by NAME at HH:MM · note" from the database. |
| 18 | Reports inbox | ✅ | Report times are relative to when the demo was seeded. |
| 19 | Report open | ✅ | Opening does not mark it read. |
| 20 | All read | ✅ | |
| 21 | Team | ✅ | Footnote says permissions apply instantly (they are pushed live). |
| 22 | Permissions sheet | ✅ | |
| 23 | Add member sheet | ✅ | Creates a real account. |
| 24 | Notifications | ✅ | Latest five open alerts. |
| 25 | Assistant, empty | ✅ | Plus PDF and microphone buttons. |
| 26 | Assistant answer with chart | ✅ | Real tool calls, chart, citations, approval card and follow-ups. |
| 30 | Worker Today | ✅ | Shift text depends on the time: outside 06:00–14:00 it says "You're off shift right now", as in the prototype's code. |
| 31 | Worker alerts | ✅ | Water alerts only. |
| 32 | Shift report validation | ✅ | |
| 33 | Worker basin detail | ✅ | Probes list and "Report a problem" instead of finances. |
| 40 | Technician Today | ✅ | |
| 41 | Hardware alerts | ✅ | |
| 42 | Sensor health | ✅ | Evidence comes from the health job ("+0.15 vs. its 7-day baseline" instead of "vs. neighbour basins"). |
| 43 | Maintenance | ✅ | The aerator task is assigned to Karim (decision 11). |
| 50 | Phone website hero | ✅ | |
| 51 | Phone sign in | ✅ | |
| 52 | Phone owner overview | ✅ | |
| 53 | Phone alerts | ✅ | |
| 54 | Phone assistant | ✅ | |

Fixes made during this check: the "just resolved" state, the team order (workers by shift, then technicians), the order of
maintenance tasks, the number format of the prediction features, the width of the "Explain this estimate" button, the four starter chips
of the assistant, the chart time labels for long series, shorter source chips, and a calmer Basin 3 day-night swing so its night alert
is "high" as in the design (not "critical").
