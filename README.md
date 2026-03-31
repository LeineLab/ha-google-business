# Google Business Profile — Home Assistant Integration

Manage your Google Business Profile posts directly from Home Assistant automations and scripts.

## Prerequisites

### 1. Google Cloud Project Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the following APIs:
   - **Google My Business API** (`mybusiness.googleapis.com`)
   - **My Business Account Management API** (`mybusinessaccountmanagement.googleapis.com`)
   - **My Business Business Information API** (`mybusinessbusinessinformation.googleapis.com`)

> **Note:** The Google My Business API requires special access. Submit an access request at
> https://support.google.com/business/contact/api_default
> Google reviews these requests manually — approval may take several business days.
>
> You can add the integration before access is approved. It will show as **"pending"** and
> activate automatically once Google approves your request — no need to re-authenticate.

### 2. OAuth 2.0 Credentials

1. In the Cloud Console, navigate to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth 2.0 Client ID**
3. Set **Application type** to **Web application**
4. Add the following **Authorized redirect URI**:
   ```
   https://my.home-assistant.io/redirect/oauth
   ```
5. Save and copy your **Client ID** and **Client Secret**

---

## Installation

### Via HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations → Custom repositories**
3. Add `https://github.com/LeineLab/ha-google-business` as an **Integration**
4. Search for "Google Business Profile" and install

### Manual

1. Copy `custom_components/google_business/` into your HA `config/custom_components/` directory
2. Restart Home Assistant

---

## Configuration

1. In Home Assistant, go to **Settings → Integrations → Application Credentials**
2. Click **Add Application Credential** and select **Google Business Profile**
3. Enter your **Client ID** and **Client Secret**
4. Go to **Settings → Integrations → Add Integration**, search for **Google Business Profile**
5. Follow the OAuth flow to authorize access
6. If you have multiple locations, select the one you want to manage

Each configured entry represents one Google Business location.

### API access not yet approved

If your API access request is still pending when you run the setup flow, you will be shown an **"API access pending"** step. Click **Submit** to add the integration anyway — it will appear as **"Google Business Profile (pending)"** with status **"Setup retrying"**. Once Google approves your request, Home Assistant will automatically resolve the location and activate the integration on its next retry (checked once per hour).

---

## Services

### `google_business.create_post`

Creates a new post on your Google Business Profile.

**Response:** Returns `post_name` (the resource name of the created post, useful for later updates/deletes).

| Field | Required | Description |
|-------|----------|-------------|
| `config_entry_id` | No* | Config entry ID (required with multiple locations) |
| `post_type` | Yes | `standard`, `event`, `offer`, or `alert` |
| `summary` | Yes | Main text of the post |
| `language_code` | No | BCP-47 language code (default: `en`) |
| `call_to_action_type` | No | `none`, `book`, `order`, `learn_more`, `sign_up`, `call` |
| `call_to_action_url` | No | URL for the CTA button |
| `event_title` | No | Title (required for `event` posts) |
| `event_start` | No | Event start date/time |
| `event_end` | No | Event end date/time |
| `coupon_code` | No | Coupon code (`offer` posts) |
| `redeem_online_url` | No | Redeem URL (`offer` posts) |
| `terms_conditions` | No | Terms and conditions (`offer` posts) |

**Example:**
```yaml
action: google_business.create_post
data:
  post_type: standard
  summary: "We're open this weekend! Come visit us."
  language_code: de
  call_to_action_type: learn_more
  call_to_action_url: "https://example.com"
response_variable: post_result
```

---

### `google_business.update_post`

Updates an existing post using its resource name.

| Field | Required | Description |
|-------|----------|-------------|
| `config_entry_id` | No* | Config entry ID |
| `post_name` | Yes | Resource name (e.g. `accounts/123/locations/456/localPosts/789`) |
| `summary` | No | New post text |
| `language_code` | No | Updated language code |
| `call_to_action_type` | No | Updated CTA type |
| `call_to_action_url` | No | Updated CTA URL |
| `event_title` | No | Updated event title |
| `event_start` | No | Updated event start |
| `event_end` | No | Updated event end |
| `coupon_code` | No | Updated coupon code |
| `redeem_online_url` | No | Updated redeem URL |
| `terms_conditions` | No | Updated terms |

**Example:**
```yaml
action: google_business.update_post
data:
  post_name: "{{ post_result.post_name }}"
  summary: "Updated: We're open this weekend and Monday too!"
```

---

### `google_business.delete_post`

Deletes a post from your Google Business Profile.

| Field | Required | Description |
|-------|----------|-------------|
| `config_entry_id` | No* | Config entry ID |
| `post_name` | Yes | Resource name of the post to delete |

**Example:**
```yaml
action: google_business.delete_post
data:
  post_name: "{{ post_result.post_name }}"
```

---

## Automation Example

```yaml
automation:
  - alias: "Post weekly special"
    trigger:
      - platform: time
        at: "09:00:00"
        # Only on Mondays
    condition:
      - condition: template
        value_template: "{{ now().weekday() == 0 }}"
    action:
      - action: google_business.create_post
        data:
          post_type: standard
          summary: "This week's special: 20% off all services!"
          language_code: de
          call_to_action_type: call
        response_variable: result
      - action: persistent_notification.create
        data:
          message: "Post created: {{ result.post_name }}"
```

---

## Troubleshooting

- **API not enabled**: If the setup flow shows an "API not enabled" error with a direct link, click it to enable the `mybusiness.googleapis.com` API in your Google Cloud project, wait a minute, then try adding the integration again.
- **`cannot_fetch_locations`**: Your OAuth credentials may not have access to the required APIs. Verify all three APIs listed in the prerequisites are enabled.
- **`no_locations`**: The Google account has no Business Profile locations associated with it.
- **401 errors**: Re-authenticate via **Settings → Integrations → Google Business Profile → Re-authenticate**.
- **403 errors**: API access may be restricted. Check your Google Cloud Console quotas and API enablement.
