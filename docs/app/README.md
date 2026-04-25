# App Docs

This folder contains application-specific documentation for the WiMLDS automation system.

## Package Organization

The app is organized by domain so related code stays together.

- `agents/publishing/`: publishing and outreach workflows
- `agents/event_ops/`: conferencing, reminders, and event execution
- `agents/post_event/`: post-event processing and analytics
- `integrations/meta/`: Meta integrations
- `integrations/meeting/`: Zoom, Teams, and Google Meet integrations
- `integrations/storage/`: Drive and storage integrations
- `integrations/llm/`: language model integrations
- `integrations/processing/`: transcript and processing helpers

## CLI

Use the repository root CLI for most actions:

- `python run.py event ...`
- `python run.py social ...`
- `python run.py post-event-agent ...`
- `python run.py langgraph ...`
- `python run.py analytics ...`

## Contents

- `USER_GUIDE.md`: end-user and operator guidance
- `INSTALL_WINDOWS.md`: Windows setup instructions
- `SECURITY.md`: security and credential handling notes
- `AI_SOCIAL_POSTING_AGENT.md`: feature-specific reference for the social posting workflow
