import os
import yaml
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/adwords"]
TOKEN_FILE = 'token.json'
GOOGLE_ADS_YAML_FILE = 'google-ads.yaml'

def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("refreshing credentials")
            creds.refresh(Request())
        else:
            client_config = {
                "installed": {
                    "client_id": os.getenv('CLIENT_ID'),
                    "client_secret": os.getenv('CLIENT_SECRET'),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"]
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=8080, prompt='consent', authorization_prompt_message='', login_hint='email_address')
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return creds

def update_google_ads_yaml(client_id, client_secret, refresh_token):
    if os.path.exists(GOOGLE_ADS_YAML_FILE):
        with open(GOOGLE_ADS_YAML_FILE, 'r') as f:
            config = yaml.safe_load(f)
    else:
        config = {}

    if 'client_id' in config and 'client_secret' in config and 'refresh_token' in config:
        if (config['client_id'] == client_id and
            config['client_secret'] == client_secret and
            config['refresh_token'] == refresh_token):
            print("Credentials are already up-to-date. Skipping update.")

    config['client_id'] = client_id
    config['client_secret'] = client_secret
    config['refresh_token'] = refresh_token

    with open(GOOGLE_ADS_YAML_FILE, 'w') as f:
        yaml.dump(config, f)
    print("Updated credentials in google-ads.yaml.")

def main():
    
    credentials = get_credentials()

    if credentials:
        update_google_ads_yaml(credentials.client_id, credentials.client_secret, credentials.refresh_token)
        
        print("Refresh Token:", credentials.refresh_token)
    else:
        print("Failed to retrieve credentials.")

if __name__ == "__main__":
    main()