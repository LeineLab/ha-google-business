"""Constants for the Google Business Profile integration."""

DOMAIN = "google_business"

# Config entry data keys
CONF_LOCATION_NAME = "location_name"
CONF_ENTRY_ID = "config_entry_id"

# Service names
SERVICE_CREATE_POST = "create_post"
SERVICE_UPDATE_POST = "update_post"
SERVICE_DELETE_POST = "delete_post"

# Post types
POST_TYPE_STANDARD = "standard"
POST_TYPE_EVENT = "event"
POST_TYPE_OFFER = "offer"
POST_TYPE_ALERT = "alert"

POST_TYPES = [POST_TYPE_STANDARD, POST_TYPE_EVENT, POST_TYPE_OFFER, POST_TYPE_ALERT]

# Call-to-action types
CTA_TYPE_NONE = "none"
CTA_TYPE_BOOK = "book"
CTA_TYPE_ORDER = "order"
CTA_TYPE_LEARN_MORE = "learn_more"
CTA_TYPE_SIGN_UP = "sign_up"
CTA_TYPE_CALL = "call"

CTA_TYPES = [
    CTA_TYPE_NONE,
    CTA_TYPE_BOOK,
    CTA_TYPE_ORDER,
    CTA_TYPE_LEARN_MORE,
    CTA_TYPE_SIGN_UP,
    CTA_TYPE_CALL,
]

# API base URLs
API_BASE_URL = "https://mybusiness.googleapis.com/v4/"
ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"

# OAuth scope
OAUTH_SCOPE = "https://www.googleapis.com/auth/business.manage"

# Guard flag for service registration
SERVICES_REGISTERED = "services_registered"
