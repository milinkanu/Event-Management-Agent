# X Agent Integration Guide

## Purpose

This document explains:

- how the current event-management project works
- what the main nodes and agents are
- how those pieces coordinate with each other
- what X/Twitter-related code already exists
- how your current external `X_agent` can be integrated into this repository

It also uses the external guide at:

- `d:\X_Agent_18032026\X_Agent_buffer\PROJECT_GUIDE.md`

to compare the current standalone X workflow with the existing WiMLDS event-management architecture.


## 1. What This Project Is Right Now

This repository is not a single web app. It is primarily a Python automation system for managing the full lifecycle of an event.

The current project is centered around:

- event ingestion from a master sheet or Excel workbook
- event creation on Meetup
- QR generation
- poster generation
- social and WhatsApp publishing
- conferencing setup
- reminder scheduling
- event-day execution
- post-event content generation
- analytics collection

The main package is:
  
- `wimlds/`

The main entry point is:

- `run.py`

which simply calls:

- `wimlds/cli.py`

So the real operational control surface is the CLI, not a frontend dashboard.


## 2. High-Level Folder Structure

### Root-level meaning

- `wimlds/`: main application code
- `docs/`: project and app documentation
- `diagrams/`: architecture and workflow images
- `shared-modules/`: reusable helpers, mainly Drive-related
- `wimlds_poc_demo/`: demo/proof-of-concept version with sample outputs

### Inside `wimlds/`

- `agents/`: business workflow agents
- `core/`: orchestration, logging, sheet access, result/state utilities
- `integrations/`: external service connectors
- `config/`: settings, templates, assets
- `tests/`: test suite


## 3. The Real Mental Model

The system works like this:

1. Load one event row from the master sheet or Excel.
2. Validate that required fields exist.
3. Run a sequence of agents that create assets and publish information.
4. Store intermediate outputs back into `event_data`.
5. Write important outputs back to the sheet.
6. Continue later lifecycle stages using the enriched `event_data`.

The important shared object is:

- `event_data` dictionary

This is the glue between agents.

Examples of values passed through `event_data`:

- event title, date, venue, speaker metadata
- `meetup_event_id`
- `meetup_event_url`
- `_qr_local_path`
- `_poster_local_path`
- `conference_link`
- `blog_link`
- `recording_link`
- `_twitter_tweet_id` (expected by analytics, but not properly written today)


## 4. Main Entry Points

### CLI entry

The supported CLI lives in:

- `wimlds/cli.py`

Key commands:

- `python run.py event --event-id <row>`
- `python run.py social --event-id <row> --stage announcement`
- `python run.py langgraph --event-id <row>`
- `python run.py post-event-agent --event-id <row>`
- `python run.py analytics --event-id <row>`

### Two orchestration styles exist

There are really two orchestration styles in the repo:

1. The full event LangGraph pipeline:
   - `wimlds/core/langgraph_orchestrator.py`
2. A smaller social Meta-posting graph:
   - `wimlds/graph.py`

The full event LangGraph pipeline is the important one for the project.


## 5. The Main Event Nodes and How They Coordinate

The full workflow graph is defined in:

- `wimlds/core/langgraph_orchestrator.py`

### Full node order

The current main nodes are:

1. `validate`
2. `create_event`
3. `generate_qr`
4. `create_poster`
5. `approve_poster`
6. `upload_poster`
7. `announce`
8. `setup_conferencing`
9. `schedule_reminders`
10. `event_execution`
11. `post_event`
12. `analytics`
13. terminal nodes: `completed`, `failed`, `halted`

### What each node does

#### `validate`

File:

- `wimlds/core/langgraph_orchestrator.py`
- uses `wimlds/core/sheets_client.py`

Work:

- reads event row from Google Sheets or Excel fallback
- checks required fields like title, date, time, mode, speaker
- if fields are missing, halts the pipeline
- may notify organizer about missing fields

#### `create_event`

File:

- `wimlds/agents/publishing/meetup_agent.py`

Work:

- creates or updates the Meetup event
- returns `meetup_url` and `event_id`
- enriches state so later nodes can use the Meetup URL and ID

#### `generate_qr`

File:

- `wimlds/agents/publishing/qr_agent.py`

Work:

- generates a QR code from the Meetup URL
- uploads the QR to Drive
- returns a local QR path and Drive URL

#### `create_poster`

File:

- `wimlds/agents/publishing/poster_agent.py`

Work:

- creates the poster image
- embeds event details and QR
- uploads to Drive
- keeps local poster file path for later use

#### `approve_poster`

File:

- `wimlds/core/langgraph_orchestrator.py`

Work:

- checks poster approval status from sheet
- loops while waiting
- routes back to poster creation on rework
- continues only after approval

#### `upload_poster`

File:

- `wimlds/agents/publishing/meetup_agent.py`

Work:

- uploads approved poster to Meetup event

#### `announce`

Files:

- `wimlds/core/langgraph_orchestrator.py`
- `wimlds/agents/publishing/social_agent.py`
- `wimlds/agents/publishing/whatsapp_agent.py`

Work:

- sends the event announcement across enabled channels
- today this is the main place where X/Twitter posting happens
- social success is treated as important
- WhatsApp failure is currently treated as non-blocking in the LangGraph node

#### `setup_conferencing`

Files:

- `wimlds/core/langgraph_orchestrator.py`
- `wimlds/integrations/meeting/zoom_client.py`
- `wimlds/integrations/meeting/gmeet_client.py`

Work:

- creates Zoom or Google Meet links for online/hybrid events
- skips for in-person events

#### `schedule_reminders`

Files:

- `wimlds/core/langgraph_orchestrator.py`
- `wimlds/agents/event_ops/reminders_agent.py`

Work:

- placeholder/scheduler integration area
- intended for T-2d, T-1d, and T-2h reminders

#### `event_execution`

Files:

- `wimlds/core/langgraph_orchestrator.py`
- `wimlds/agents/publishing/social_agent.py`
- `wimlds/agents/publishing/whatsapp_agent.py`

Work:

- sends final bump messages
- marks event as in progress

#### `post_event`

File:

- `wimlds/agents/post_event/post_event_agent.py`

Work:

- fetches recording/transcript
- runs LLM summarization
- generates blog
- uploads assets to Drive
- posts public gratitude content
- sends attendee-only resource updates

#### `analytics`

File:

- `wimlds/agents/post_event/analytics_agent.py`

Work:

- gathers event KPIs
- fetches social engagement metrics
- writes analytics back
- marks event completed


## 6. How Coordination Actually Works Between Nodes

The coordination model is simple but effective:

- `validate` loads base event row
- each next node reads `state["event_data"]`
- each agent returns an `AgentResult`
- the orchestrator merges `result.data` into `event_data`
- routing logic decides the next node

This means the project is not using deep message passing or distributed agents. It is using:

- one shared mutable event state
- sequential execution
- conditional routing

That shared-state design is why X integration should be added in a way that writes back tweet metadata into `event_data` and the sheet.


## 7. Important Files and What They Do

### Core files

- `run.py`: repository entry point
- `wimlds/cli.py`: main command interface
- `wimlds/core/langgraph_orchestrator.py`: full event workflow graph
- `wimlds/core/orchestrator.py`: shared `AgentResult`
- `wimlds/core/sheets_client.py`: sheet/excel read-write layer
- `wimlds/config/settings.py`: environment-based config
- `wimlds/config/message_templates.py`: social message template rendering

### Publishing files

- `wimlds/agents/publishing/meetup_agent.py`: Meetup lifecycle
- `wimlds/agents/publishing/qr_agent.py`: QR generation
- `wimlds/agents/publishing/poster_agent.py`: poster generation
- `wimlds/agents/publishing/social_agent.py`: LinkedIn, Facebook, X, Instagram, Meetup groups, WhatsApp broadcast
- `wimlds/agents/publishing/whatsapp_agent.py`: WhatsApp delivery
- `wimlds/agents/publishing/facebook_node.py`: Meta graph Facebook node
- `wimlds/agents/publishing/instagram_node.py`: Meta graph Instagram node
- `wimlds/agents/publishing/caption_agent.py`: social caption generation for the small Meta graph

### Post-event files

- `wimlds/agents/post_event/post_event_agent.py`: post-event content and distribution
- `wimlds/agents/post_event/analytics_agent.py`: KPI collection and reporting

### Integration files

- `wimlds/integrations/meta/meta_api.py`: helper for Meta Graph posting
- `wimlds/integrations/meeting/*`: Zoom, GMeet, Teams integrations
- `wimlds/integrations/storage/drive_client.py`: Drive storage helper
- `wimlds/integrations/llm/llm_client.py`: model wrapper

### Tests that matter for X/social work

- `wimlds/tests/publishing/test_social_whatsapp.py`
- `wimlds/tests/post_event/test_analytics_agent.py`
- `wimlds/tests/core/test_langgraph_orchestrator.py`


## 8. Existing X/Twitter Structure Already Present

There is already some X support in this repo, but it is incomplete and scattered.

### What already exists

#### A. X is already a supported social channel

File:

- `wimlds/agents/publishing/social_agent.py`

Current behavior:

- checks `promote_x`
- generates event-stage message text
- posts to X using Tweepy
- truncates to 280 characters

#### B. The sheet model already supports an X enable/disable flag

File:

- `wimlds/core/sheets_client.py`

Mapping:

- `x_twitter_y_n` -> `promote_x`

So the pipeline already knows whether X should be used for an event.

#### C. Analytics expects tweet metrics

File:

- `wimlds/agents/post_event/analytics_agent.py`

It expects:

- `_twitter_tweet_id`

and fetches:

- impressions
- likes
- retweets

#### D. The CLI already exposes Twitter as a social channel

File:

- `wimlds/cli.py`

So operationally, X is already treated as a first-class target during social posting.


## 9. What Is Missing in the Current X Implementation

This is the most important part for your integration work.

### Missing piece 1: there is no dedicated `x_agent.py`

Right now X posting lives inside:

- `wimlds/agents/publishing/social_agent.py`

That means:

- no dedicated abstraction
- no X-specific retries
- no X-specific analytics/writeback handling
- no clean place to plug in your external X workflow

### Missing piece 2: X post metadata is not properly written back

`SocialAgent._post_twitter()` currently returns only `True/False`.

So it does not preserve:

- tweet id
- tweet URL
- raw API response

But analytics later expects:

- `_twitter_tweet_id`

This is an architectural gap.

### Missing piece 3: current X posting is text-only

The current `_post_twitter()` method posts only text.

Your external `X_agent` supports:

- AI rewriting
- Buffer publishing
- optional image handling
- analytics/scraping
- Excel-driven queueing

That is much richer than the current built-in X handling.

### Missing piece 4: no X-specific node in the LangGraph pipeline

The main workflow has:

- one `announce` node

Inside that node, all social posting is bundled together.

So there is no isolated node such as:

- `announce_x`
- `x_publish`
- `x_analytics`

### Missing piece 5: current post-event analytics may never see real tweet IDs

Since tweet ID is not stored during posting, the later analytics fetch can silently return zeros.


## 10. Meta Platform Status: What Looks Connected and What Looks Risky

You mentioned that Meta platforms seem connected and working.

That is partly true, but there are two separate Meta implementations.

### The practical Meta path

File:

- `wimlds/agents/publishing/social_agent.py`

This appears to be the more operational path.

It posts directly to:

- Facebook Page
- Instagram

using tokens from `settings.py`.

### The smaller Meta LangGraph path

Files:

- `wimlds/graph.py`
- `wimlds/agents/publishing/facebook_node.py`
- `wimlds/agents/publishing/instagram_node.py`
- `wimlds/integrations/meta/meta_api.py`

This is a smaller graph:

1. generate caption
2. post Instagram
3. post Facebook

### Important risk

`meta_api.py` expects settings fields like:

- `meta_access_token`
- `meta_graph_version`
- `instagram_business_account_id`

But those fields are not declared in the current `wimlds/config/settings.py`.

So:

- the small dedicated Meta graph may be outdated or partially broken
- the general `SocialAgent` route is more likely to be the live path


## 11. What Your External X Agent Does

Based on `PROJECT_GUIDE.md`, your external X project is a standalone local command center with:

- FastAPI backend
- static browser dashboard
- AI rewriting
- Buffer publishing to X
- X scraping and audience analytics
- Excel sync and review queue
- image processing pipeline

Main orchestration file there:

- `server.py`

Important external modules:

- `ai_rewriter.py`
- `buffer_client.py`
- `scraper.py`
- `image_processor.py`
- `validator.py`
- `link_generator.py`

So your X project is stronger in:

- operator dashboard UX
- Buffer-based publish flow
- AI rewrite workflow
- X-focused analytics
- review-before-publish queue

The WiMLDS repo is stronger in:

- end-to-end event lifecycle orchestration
- event sheet integration
- Meetup/QR/poster/reminder flow
- post-event pipeline


## 12. Best Integration Strategy for Your Current X Agent

The best path is not to replace the whole WiMLDS system.

The best path is:

- keep WiMLDS as the master event orchestration system
- integrate your X agent as a dedicated publishing and analytics subsystem

### Recommended architecture

Create a dedicated module:

- `wimlds/agents/publishing/x_agent.py`

This new agent should become the single X interface inside this repo.

Then:

- `SocialAgent` should call `XAgent` instead of posting to Tweepy directly
- LangGraph `announce` node can remain unchanged at first
- post-event analytics should read tweet metadata written by `XAgent`

### Why this is the best option

Because it:

- fits the existing architecture
- avoids replacing the whole pipeline
- preserves one source of truth for event state
- lets you reuse your existing X logic cleanly
- keeps future migration incremental


## 13. Recommended Integration Phases

### Phase 1: Create a repo-native `XAgent`

Create:

- `wimlds/agents/publishing/x_agent.py`

Responsibilities:

- accept `event_data`, text, stage, optional image
- choose publish mode
- return structured result

Recommended return shape:

```python
{
    "success": True,
    "tweet_id": "...",
    "tweet_url": "...",
    "platform": "x",
    "provider": "buffer",
    "raw_response": {...},
}
```

### Phase 2: Replace `SocialAgent._post_twitter()`

Current file:

- `wimlds/agents/publishing/social_agent.py`

Change it so that:

- `_post_twitter()` calls `XAgent.publish(...)`
- it captures tweet ID and tweet URL
- it writes those into the social results

### Phase 3: Write tweet metadata back into `event_data`

This is critical.

During announce flow, persist:

- `_twitter_tweet_id`
- `_twitter_post_url`
- maybe `_twitter_provider`

Without this, analytics remains weak.

### Phase 4: Write X outputs back to sheet

Add sheet columns if needed for:

- `twitter_post_url`
- `twitter_tweet_id`
- `twitter_status`

Then write them through:

- `wimlds/core/sheets_client.py`

### Phase 5: Use your external X rewrite logic

You have two options here.

#### Option A: Port key logic into this repo

Move/adapt:

- rewrite logic
- image processing logic
- Buffer client logic

into native `wimlds` modules.

Best for:

- long-term maintainability
- fewer moving parts

#### Option B: Call the external X FastAPI service

WiMLDS can call your existing X service over HTTP.

Best for:

- faster initial integration
- preserving current dashboard and code

Tradeoff:

- extra service dependency
- two codebases to deploy/run

My recommendation is:

- start with Option B if you need fast integration
- move toward Option A once the contract stabilizes


## 14. Suggested Concrete Design for `XAgent`

### Suggested methods

```python
class XAgent:
    def rewrite_post(self, event_data: dict, stage: str) -> dict: ...
    def process_image(self, image_path_or_url: str) -> str: ...
    def publish(self, text: str, image_url: str | None = None) -> dict: ...
    def collect_post_metrics(self, tweet_id: str) -> dict: ...
    def run_event_publish(self, event_data: dict, stage: str) -> dict: ...
```

### Suggested `run_event_publish()` behavior

1. Build stage-specific text from WiMLDS event data.
2. Optionally rewrite it using your X rewrite service.
3. Optionally prepare image.
4. Publish using Buffer or direct X API.
5. Return tweet metadata.
6. Update `event_data` with IDs and URLs.


## 15. Best Places to Reuse Your Current X Agent Features

### Reuse 1: AI rewrite

Use your rewrite logic to improve:

- announcement posts
- spotlight posts
- logistics posts
- final bump posts
- maybe post-event X recap posts later

### Reuse 2: Buffer posting

This is a good fit if:

- you want a stable operational posting layer
- you want account/channel abstraction
- you want easier media publishing than raw API handling

### Reuse 3: X analytics/scraper

This should be integrated carefully because the WiMLDS analytics stage is post-event focused.

Best usage:

- add optional X campaign analytics for the `announce` stage
- store those outputs separately from post-event attendance KPIs

### Reuse 4: Excel review flow

This is useful, but do not let it replace the main event sheet pipeline entirely.

Better pattern:

- WiMLDS remains source of truth for events
- your X review flow becomes an approval layer for X copy only


## 16. Recommended Changes in Existing Files

### File: `wimlds/agents/publishing/social_agent.py`

Recommended changes:

- extract X logic out of `_post_twitter()`
- call dedicated `XAgent`
- return metadata, not only bool

### File: `wimlds/core/langgraph_orchestrator.py`

Recommended changes:

- keep `announce` node at first
- later optionally split into:
  - `announce_social`
  - `announce_x`
  - `announce_whatsapp`

If you want minimal disruption, do not split immediately.

### File: `wimlds/agents/post_event/analytics_agent.py`

Recommended changes:

- consume actual stored tweet ID
- optionally add provider-aware metric fetching
- if using Buffer, map Buffer result to final tweet ID or tweet URL

### File: `wimlds/core/sheets_client.py`

Recommended changes:

- add any new X columns to your sheet header conventions
- ensure write-back support for new X metadata fields

### New file: `wimlds/agents/publishing/x_agent.py`

This should be the main integration surface for your work.

### Optional new file: `wimlds/integrations/x/buffer_client.py`

If you port Buffer logic into this repo, keep provider/integration code separate from agent logic.


## 17. Replacement vs Reuse: What Should You Replace?

### Replace

- the current `_post_twitter()` boolean-only implementation

### Reuse

- event orchestration
- sheet loading
- announcement stage placement
- existing `promote_x` flag
- analytics stage skeleton

### Do not replace immediately

- the whole LangGraph workflow
- Meetup, QR, poster, or post-event pipeline


## 18. Suggested Minimal First Implementation

If you want the fastest useful integration, do this:

1. Create `wimlds/agents/publishing/x_agent.py`.
2. Make it call your current external FastAPI X service.
3. Replace `SocialAgent._post_twitter()` with `XAgent.publish()`.
4. Store `_twitter_tweet_id` and `_twitter_post_url` in event data and sheet.
5. Update analytics to use those stored values.

This gives you:

- real X integration
- reuse of your current X system
- minimal disturbance to WiMLDS structure


## 19. Suggested Long-Term Clean Architecture

Long term, the cleanest structure would be:

- `wimlds/agents/publishing/x_agent.py`
- `wimlds/integrations/x/`
  - `buffer_client.py`
  - `x_api_client.py`
  - `x_rewriter.py`
  - `x_analytics.py`

And then:

- `SocialAgent` becomes a channel coordinator
- each platform gets a dedicated agent/integration

That is more maintainable than keeping X logic buried inside one large social agent.


## 20. Final Recommendation

Your current external X agent is valuable and should be integrated, not ignored.

The cleanest approach is:

- treat WiMLDS as the main event orchestration system
- add a dedicated repo-native `XAgent`
- initially let that `XAgent` call your existing external FastAPI/Buffer workflow
- replace the current direct Tweepy posting path
- persist tweet metadata properly
- then optionally migrate external X logic into this repo in stages

In short:

- the current repo already has partial X support
- it does not yet have a proper X agent
- the right integration point is the `announce` flow through `SocialAgent`
- the biggest missing piece is structured X write-back and analytics continuity


## 21. Files You Should Read First for Your X Integration Work

Read these in order:

1. `wimlds/core/langgraph_orchestrator.py`
2. `wimlds/agents/publishing/social_agent.py`
3. `wimlds/core/sheets_client.py`
4. `wimlds/agents/post_event/analytics_agent.py`
5. `wimlds/cli.py`
6. `d:\X_Agent_18032026\X_Agent_buffer\PROJECT_GUIDE.md`
7. your external `server.py`, `buffer_client.py`, and `ai_rewriter.py`


## 22. Bottom Line

There is no true `X_agent` inside this repo yet.

What exists today is:

- an embedded X posting method inside `SocialAgent`
- a sheet flag for enabling X
- analytics code that expects tweet metadata

So your work should focus on turning that partial support into a proper X subsystem.

The safest and strongest path is:

- create `x_agent.py`
- integrate your current external X workflow through it
- preserve the existing event-management orchestration
- improve metadata persistence so X posting and analytics form one connected lifecycle
