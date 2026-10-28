# Axon UI / visual improvement list (running log)
Collected 2026-10-09 while using Axon as the SANKET marketing team. Observations only from what was on screen. Severity: H = hurts real work, M = noticeable friction, L = polish.

## A. Reading and moving long answers (chat panel)
1. [H] Long replies are hard to read. The panel is narrow and docked to the right; a 1,800 word plan needs dozens of scroll steps. Add a widen / full-screen reader mode and a "pop out to document" action.
2. [H] Mouse-wheel scrolling inside a long reply moves only a few lines per tick. Scrolling 100 ticks barely crossed one section. Raise scroll step, add Page Up/Down and Home/End support, and a scrub bar.
3. [H] No "copy whole conversation" or "export reply as .md/.docx". Copy exists only per message and only when hovering. Ctrl+A copies only the messages currently rendered (the thread is virtualised), so selecting all silently drops the long reply unless it is on screen. Add "Copy all", "Export thread", and "Save reply to project folder".
4. [M] Section titles in answers (for example "IDEAL CUSTOMER PROFILE PER VERTICAL") render like body text. Headings, tables and numbered steps should get real typographic hierarchy, and structured results (plans, email sequences) should render as cards with a copy button each.
5. [M] The floating "Latest messages" pill overlaps the last lines of text it is meant to jump to. Give it its own row above the input and hide it when already at the bottom.
6. [M] Merge fields: a line containing only {observation} was rendered as "(observation)" in the chat while "{first_name}" kept its braces. Template placeholders should never be altered. Render inline code style for placeholders.
7. [L] The long first message you send is shown as one large blue block with no collapse. Add "Show more / Show less" for long user messages.

## B. Reliability signals
8. [H] A reply can finish as "Completed" after one line of preamble ("I'll outline... and check the guidance") with no actual deliverable (seen with GPT-6.1-Sol on the first request). Nothing flagged that the answer was incomplete. Detect "turn ended with no substantive output" and show a banner with a one-click "Continue" / "Retry".
9. [M] Status vocabulary is inconsistent: panel chip says "Completed", the map label says "Idle", the Multi Agents tab says "0 active · 0 waiting · 2 completed". Pick one state model and use the same words and colours everywhere.
10. [M] "1 coworkers active" is ungrammatical (plural noun with 1). Use proper plurals.
11. [M] Context information is duplicated: "12% context" under the name, and "127.6K / 1.1M · 44.6K tokens" in the footer. Merge into one meter with a tooltip, and explain what "44.6K tokens" refers to (this turn? this thread?).
12. [M] Long waits show only "Thinking". Show elapsed time and what step is running (reading, drafting, calling a colleague). Offer a "notify me when done" toggle so people can walk away.

## C. Model picker
13. [H] After typing a search and pressing Enter quickly, "Manage models" can be what gets activated instead of the first match (it opened Settings > Models & API keys when the list had not finished filtering). Keyboard selection must always target the first model result, never an action row, and Manage models should be visually separated (and not keyboard-default).
14. [M] The chosen model carries over to the next colleague you open (DeepSeek Flash stayed selected for the SDR). That is convenient but surprising; show a small "model: X (inherited)" hint, or let each role keep its own default.
15. [L] Rows show a marketing name plus a technical id in grey (good), but groups are long and unsorted by capability. Add a "Recently used" row and small chips for speed/depth.

## D. The 3D office map
16. [H] Clicking near a team board unexpectedly flew the camera to another zone (Commons lounge) and opened a "Team tasks" panel, losing the person being targeted. Make targets forgiving: bigger hit areas, a short hover label, and never move the camera on a board click.
17. [M] Name tags overlap and truncate ("Sales Development Repre..."), and tags sit on top of other people at close zoom. Use collision-aware label placement, abbreviate consistently, and show the full role on hover.
18. [M] Many avatars look alike at the default zoom, so finding a specific colleague by eye is slow. The search box is good; add role-coloured rings or small role icons on avatars.
19. [M] The map pans and zooms under the cursor during ordinary clicks and drags (every drag in the corner moves the scene). Add a "lock camera" toggle.
20. [L] Department labels on the floor ("Marketing 20 people", "Growth & Outreach 5 people") are clear in the overview but fade, tilt and get hidden behind plants and desks when zoomed in. Keep a screen-space breadcrumb instead.

## E. Layout and chrome
21. [M] The right panel covers about 40% of the window and cannot be resized, so the office you are supposed to watch is mostly hidden while working. Add a drag handle, a dock-left/dock-right choice, and a compact mode.
22. [M] The "More" department chip keeps a red/orange outline even when idle, which reads like an error or focus ring. Use a neutral style and show the outline only on keyboard focus.
23. [M] The top bar has a very wide search plus a department dropdown plus six chips; at normal widths this crowds the right-side icons. Collapse chips into the dropdown on smaller windows.
24. [M] "Team tasks" panel: the heading and the task row are clipped and a horizontal scrollbar appears. Wrap text instead.
25. [L] Floating cards on the left ("Your team is ready", "Ask Axon Ctrl+K") are useful but visually heavy and sit over desks. Consider one slim, collapsible rail.

## F. What already works well (keep)
- Department filter, person search ("lead", "copywriter", "email market") and model search all respond instantly and are the fastest way around.
- Each colleague opens with a clear role description and suggested prompts.
- Token and context meter exists at all, which most chat apps lack.
- The Multi Agents tab (Task graph / Communication / Timeline) is a strong idea; it needs more visibility from the main view.

## G. Added late in the run (reliability, settings, connectors)
26. [H] ChatGPT-plan models (GPT-6.1-Sol, GPT-6-Luna) failed on the Research Analyst, who uses tools, with "Provider returned no response. This model may require unsupported parameters or content types". Show a capability badge in the picker ("tools: yes/no") and warn before sending, or auto-fall back to a tool-capable model.
27. [H] A colleague hit its 20-step limit and ended as "Completed" with no answer at all. A step cap needs a visible "Stopped at step limit, no final answer" state, a "Continue" button and a forced final-answer step.
28. [M] Settings > Appearance: the Theme description says "System follows..." while Light is selected, so the text and the state disagree. Describe the selected option, not a generic sentence. The page is also very sparse; density, panel width and map quality would fit here.
29. [M] Connectors: "Needs sign-in" and the orange status dot are ambiguous (error, warning or just inactive?). Use one clear status vocabulary (Connected, Needs sign-in, Error) with a legend and a one-click fix.
30. [M] Tool approval cards ("Needs You", Allow or Reject) are long when a tool needs three steps, and Ctrl+Return did not always approve. Add "Allow for this task", a compact summary line and a reliable shortcut.

## H. Suggested priority order (for the redesign session)
1. Trust first: items 8, 26, 27 (silent incomplete answers, tool failures, step-cap with no result). A pretty UI that ends "Completed" with nothing in it loses users.
2. Reading and handoff: section A (wider reading column, copy-all, export, heading hierarchy, fix the "Latest messages" overlap and the `{observation}` rendering).
3. Layout: item 21 (resizable or dockable panel), then 22 to 25 (top bar, chips, Team tasks clipping, left cards).
4. Model picker safety: section C (Enter must never open "Manage models"; do not inherit models silently between colleagues).
5. Map polish: section D (lock camera, label legibility, a click on a board should not fly the camera).
6. Settings and connectors clean-up: items 28 to 30.

## I. Redesign directions to explore together
- A calmer "reading mode" for long answers: serif or large sans body, a contents sidebar built from headings, sticky actions (Copy, Save as file, Send to HubSpot or Docs).
- Colleague cards as a consistent component: avatar, role, status chip, model chip, last result preview. The same card in the map, the search results and the Multi Agents view.
- One status language everywhere (Idle, Working, Needs you, Completed, Stopped early, Failed) with one colour and icon per state.
- A "results shelf": every finished task leaves a saved file or note that is listed in one place, instead of living only inside a chat.
- Panel as a resizable dock with a compact mode, so the 3D office stays visible while work happens.
