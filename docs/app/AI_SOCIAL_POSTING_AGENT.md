# AI Social Media Posting Agent

This guide explains how to set up Facebook Page and Instagram Business posting for the automation flow in this repository using the Meta Graph API.

It covers:
- creating a Meta developer account
- creating a Meta app using the current use-case-based flow
- configuring the required permissions
- connecting Facebook and Instagram business assets
- testing the API with Graph API Explorer
- storing credentials for this project
- understanding the LangGraph-based posting flow

This setup is intended to support the social posting components in:
- [meta_api.py](/e:/My_Projects/Python_Projects/Agentic-Event-Management/wimlds/integrations/meta_api.py)
- [facebook_node.py](/e:/My_Projects/Python_Projects/Agentic-Event-Management/wimlds/agents/facebook_node.py)
- [instagram_node.py](/e:/My_Projects/Python_Projects/Agentic-Event-Management/wimlds/agents/instagram_node.py)
- [graph.py](/e:/My_Projects/Python_Projects/Agentic-Event-Management/wimlds/graph.py)

## 1. Create A Meta Developer Account

1. Open `https://developers.facebook.com`
2. Log in with your Facebook account.
3. Complete developer registration if prompted.

Typical steps include:
- accepting the developer terms
- verifying your account if Meta asks for it

After this, you should be able to access the Meta Developer Dashboard.

## 2. Create A Meta App

1. Open `https://developers.facebook.com/apps`
2. Click `Create App`
3. Select the `Business` app type
4. Fill in the app details

Suggested values:
- App Name: `Social Event Agent`
- Contact Email: your team email

5. Click `Create App`

After creation, you will land on the app dashboard.

## 3. Add The Required Use Cases

Meta now uses a use-case-based setup flow instead of the older "Add Products" flow.

From the app dashboard:
1. Click `Add use cases`
2. Add these use cases

Required use cases:
- `Manage everything on your Page`
- `Manage messaging & content on Instagram`

These enable the APIs needed for Facebook Page publishing and Instagram Business publishing.

## 4. Configure Permissions

Open the relevant use case configuration pages and make sure these permissions are included.

Facebook Page permissions:
- `pages_show_list`
- `pages_read_engagement`
- `pages_manage_posts`
- `business_management`

Instagram permissions:
- `instagram_basic`
- `instagram_content_publish`

These permissions allow the app to:
- read page information
- publish content to a Facebook Page
- publish media on Instagram
- access Instagram business account information

## 5. Create A Facebook Page

Publishing through the Meta Graph API works with Facebook Pages, not personal profiles.

Create a page at:
`https://facebook.com/pages/create`

Example page ideas:
- `AI Events Pune`
- `Community Tech Group`

Make sure the account you use in the Meta Developer Dashboard is an admin of that page.

## 6. Convert Instagram To A Professional Account

Instagram publishing requires a Professional account, usually a Business account.

In the Instagram mobile app:
1. Open `Profile`
2. Go to `Settings and Privacy`
3. Open `Account Type`
4. Switch to `Professional`
5. Choose `Business`

## 7. Connect Instagram To The Facebook Page

Your Instagram Business account must be connected to the Facebook Page.

In Instagram:
1. Open `Settings`
2. Go to `Accounts Center`
3. Add your Facebook account
4. Select the Facebook Page you created

Expected relationship:

```text
Instagram Business Account
        |
        v
Connected to Facebook Page
```

This connection is required for Instagram Graph API publishing.

## 8. Open Graph API Explorer

Use Meta's API testing tool:

`https://developers.facebook.com/tools/explorer`

Configure it like this:
- Application: your Meta app
- Token type: user token first

## 9. Generate An Access Token

In Graph API Explorer:
1. Click `Generate Access Token`
2. Enable these permissions

Required permissions:
- `pages_show_list`
- `pages_read_engagement`
- `pages_manage_posts`
- `instagram_basic`
- `instagram_content_publish`

Approve the permission dialog.

At this point you will have a user access token. You will use that to inspect the page account details and retrieve the page access token.

## 10. Retrieve The Facebook Page ID

Run:

```http
GET /me/accounts
```

Example response:

```json
{
  "data": [
    {
      "name": "AI Events Pune",
      "id": "123456789",
      "access_token": "EAA..."
    }
  ]
}
```

Save:
- `FACEBOOK_PAGE_ID = 123456789`

Important:
- the `access_token` returned inside this response is the Page Access Token you will use for posting

## 11. Retrieve The Instagram Business Account ID

Run:

```http
GET /PAGE_ID?fields=instagram_business_account
```

Example:

```http
GET /123456789?fields=instagram_business_account
```

Example response:

```json
{
  "instagram_business_account": {
    "id": "17841400000000000"
  }
}
```

Save:
- `INSTAGRAM_BUSINESS_ACCOUNT_ID = 17841400000000000`

## 12. Verify The Token

Test the page token directly in a browser or API tool.

Example:

```text
https://graph.facebook.com/v25.0/PAGE_ID?access_token=PAGE_ACCESS_TOKEN
```

Expected response:

```json
{
  "name": "AI Events Pune",
  "id": "123456789"
}
```

If this succeeds, your token and page ID are valid.

The helper function in [meta_api.py](/e:/My_Projects/Python_Projects/Agentic-Event-Management/wimlds/integrations/meta_api.py) that maps to this check is `validate_page_token()`.

## 13. Test Facebook Publishing

Use:

```http
POST /PAGE_ID/photos
```

Parameters:
- `url=https://example.com/poster.jpg`
- `caption=Testing automated post`
- `access_token=PAGE_ACCESS_TOKEN`

If successful, the post should appear on your Facebook Page.

In this repository, the equivalent helper is:
- `post_to_facebook(image_url, caption)`

## 14. Test Instagram Publishing

Instagram publishing is a two-step flow.

### Step 1: Create Media Container

Use:

```http
POST /INSTAGRAM_BUSINESS_ACCOUNT_ID/media
```

Parameters:
- `image_url=https://example.com/poster.jpg`
- `caption=Testing Instagram post`
- `access_token=PAGE_ACCESS_TOKEN`

Example response:

```json
{
  "id": "MEDIA_CONTAINER_ID"
}
```

### Step 2: Publish The Media

Use:

```http
POST /INSTAGRAM_BUSINESS_ACCOUNT_ID/media_publish
```

Parameters:
- `creation_id=MEDIA_CONTAINER_ID`
- `access_token=PAGE_ACCESS_TOKEN`

If successful, the post will appear on Instagram.

In this repository, the equivalent helpers are:
- `create_instagram_container(image_url, caption)`
- `publish_instagram(container_id)`

## 15. Store Credentials For This Project

Store these values in `wimlds/config/.env` using the same names expected by this repository:

```ini
META_ACCESS_TOKEN=PAGE_ACCESS_TOKEN
FACEBOOK_PAGE_ID=123456789
INSTAGRAM_BUSINESS_ACCOUNT_ID=17841400000000000
META_GRAPH_VERSION=v25.0
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

You can start from:
- [`.env.example`](/e:/My_Projects/Python_Projects/Agentic-Event-Management/wimlds/config/.env.example)

These settings are loaded by:
- [settings.py](/e:/My_Projects/Python_Projects/Agentic-Event-Management/wimlds/config/settings.py)

## 16. Example Automation Flow

The social posting graph in this repo follows this sequence:

```text
Input:
  event
  description
  poster

    |
    v
Generate caption
    |
    v
Create Instagram container
    |
    v
Publish Instagram
    |
    v
Publish Facebook
```

The implementation entry point is:
- [graph.py](/e:/My_Projects/Python_Projects/Agentic-Event-Management/wimlds/graph.py)

## 17. Important Publishing Notes

Instagram Graph API publishing requires a public image URL.

Examples:

Incorrect:

```text
./posters/event.png
```

Correct:

```text
https://example.com/posters/event.png
```

This matters because:
- Instagram does not accept a local filesystem path in the Graph API call
- the image must be reachable by Meta's servers

Facebook posting in this repo is also currently implemented around image URLs in the Meta API helper.

## 18. LangGraph Usage

Once configured, the workflow can be invoked from Python with a state payload like:

```python
from graph import build_graph

graph = build_graph()
result = graph.invoke({
    "event": "AI Meetup Pune",
    "description": "A practical session on LLM applications.",
    "poster": "https://example.com/posters/ai-meetup.png",
})
```

Expected outputs include:
- `caption`
- `instagram_posted`
- `facebook_posted`
- `instagram_result`
- `facebook_result`

## 19. Future Improvements

Good next steps for this setup:
- richer AI caption generation
- hashtag generation based on topic and audience
- scheduled posting
- retry and failure handling around Meta API rate limits
- support for more social platforms
- analytics and engagement reporting

## Troubleshooting

`Missing required environment variables`
- Check that `wimlds/config/.env` contains `META_ACCESS_TOKEN`, `FACEBOOK_PAGE_ID`, and `INSTAGRAM_BUSINESS_ACCOUNT_ID`

`Instagram publishing fails for local file paths`
- Upload the image somewhere public first and pass the public URL

`Meta API request failed`
- Re-test the token in Graph API Explorer
- Verify the page and Instagram business account are connected
- Confirm the correct permissions are granted to the token
- Check whether the token has expired

`Graph import fails`
- Install `langgraph`

`Caption generation fails`
- Check that Ollama is running and reachable at `OLLAMA_BASE_URL`
- Confirm the configured `OLLAMA_MODEL` is available locally

## Related Docs

- [USER_GUIDE.md](/e:/My_Projects/Python_Projects/Agentic-Event-Management/docs/app/USER_GUIDE.md)
- [SECURITY.md](/e:/My_Projects/Python_Projects/Agentic-Event-Management/docs/app/SECURITY.md)
- [INSTALL_WINDOWS.md](/e:/My_Projects/Python_Projects/Agentic-Event-Management/docs/app/INSTALL_WINDOWS.md)

