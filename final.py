import hashlib
import pandas as pd
import os
import yaml
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
SCOPES = ["https://www.googleapis.com/auth/adwords"]
TOKEN_FILE = 'token.json'
GOOGLE_ADS_YAML_FILE = 'google-ads.yaml'

# Function to hash data using SHA-256
def hash_sha256(value):
    return hashlib.sha256(value.strip().lower().encode('utf-8')).hexdigest()

# Function to retrieve or create a custom audience segment
def get_or_create_custom_audience(client, customer_id, audience_name):
    # Initialize services
    user_list_service = client.get_service("UserListService")
    google_ads_service = client.get_service("GoogleAdsService")

    # Check if the user list already exists
    query = f"SELECT user_list.resource_name FROM user_list WHERE user_list.name = '{audience_name}'"
    response = google_ads_service.search(customer_id=customer_id, query=query)

    # If user list exists, return its resource name
    if response and response.results:
        user_list_resource_name = response.results[0].user_list.resource_name
        print(f"Found existing custom audience segment with resource name: {user_list_resource_name}")
        return user_list_resource_name

    # If user list does not exist, create a new one
    user_list_operation = client.get_type("UserListOperation")
    user_list = user_list_operation.create
    user_list.name = audience_name
    user_list.description = f"{audience_name} for marketing"
    user_list.membership_status = client.enums.UserListMembershipStatusEnum.OPEN
    user_list.crm_based_user_list.upload_key_type = client.enums.CustomerMatchUploadKeyTypeEnum.CONTACT_INFO
    user_list.membership_life_span = 30  # Days

    try:
        user_list_response = user_list_service.mutate_user_lists(
            customer_id=customer_id, operations=[user_list_operation]
        )
        user_list_resource_name = user_list_response.results[0].resource_name
        print(f"Created custom audience segment with resource name: {user_list_resource_name}")
        return user_list_resource_name
    except GoogleAdsException as ex:
        print(f"Request failed with status: {ex.error.code().name}")
        print(f"Error details: {ex.error.details()}")
        for error in ex.failure.errors:
            print(f"Error: {error.error_code} - {error.message}")
        return None

# Function to upload CSV data to the custom audience segment using OfflineUserDataJobService
def upload_csv_to_custom_audience(client, customer_id, user_list_resource_name, csv_file_path):
    offline_user_data_job_service = client.get_service("OfflineUserDataJobService")
    offline_user_data_job = client.get_type("OfflineUserDataJob")
    offline_user_data_job.type = client.enums.OfflineUserDataJobTypeEnum.CUSTOMER_MATCH_USER_LIST
    offline_user_data_job.customer_match_user_list_metadata.user_list = user_list_resource_name

    # Create the job
    create_offline_user_data_job_response = offline_user_data_job_service.create_offline_user_data_job(
        customer_id=customer_id,
        job=offline_user_data_job
    )
    offline_user_data_job_resource_name = create_offline_user_data_job_response.resource_name
    print(f"Created an offline user data job with resource name: {offline_user_data_job_resource_name}")

    # Read data from CSV file
    data = pd.read_csv(csv_file_path)
    operations = []

    for _, row in data.iterrows():
        user_data_operation = client.get_type("UserDataOperation")
        user_data = user_data_operation.create

        if pd.notna(row['Email']):
            user_identifier = client.get_type("UserIdentifier")
            user_identifier.hashed_email = hash_sha256(row['Email'])
            user_data.user_identifiers.append(user_identifier)

        offline_user_data_job_operation = client.get_type("OfflineUserDataJobOperation")
        offline_user_data_job_operation.create = user_data
        operations.append(offline_user_data_job_operation)

    # Add operations to the job
    try:
        add_offline_user_data_job_operations_response = offline_user_data_job_service.add_offline_user_data_job_operations(
            resource_name=offline_user_data_job_resource_name,
            operations=operations
        )
        print(f"Uploaded members to the offline user data job: {add_offline_user_data_job_operations_response}")

        # Run the job
        offline_user_data_job_service.run_offline_user_data_job(
            resource_name=offline_user_data_job_resource_name
        )
        print("Requested to run the offline user data job.")

    except GoogleAdsException as ex:
        print(f"Request failed with status: {ex.error.code().name}")
        print(f"Error details: {ex.error.details()}")
        for error in ex.failure.errors:
            print(f"Error: {error.error_code} - {error.message}")

# Function to get credentials
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

# Function to update google-ads.yaml
def update_google_ads_yaml(client_id, client_secret, refresh_token):
    # Load existing YAML data if file exists
    if os.path.exists(GOOGLE_ADS_YAML_FILE):
        with open(GOOGLE_ADS_YAML_FILE, 'r') as f:
            config = yaml.safe_load(f)
    else:
        config = {}

    # Check if credentials are already stored and match
    if 'client_id' in config and 'client_secret' in config and 'refresh_token' in config:
        if (config['client_id'] == client_id and
            config['client_secret'] == client_secret and
            config['refresh_token'] == refresh_token):
            print("Credentials are already up-to-date. Skipping update.")
            return  # Credentials already exist and match, no need to update

    # Update or add new credentials
    config['client_id'] = client_id
    config['client_secret'] = client_secret
    config['refresh_token'] = refresh_token

    # Write updated YAML data back to file
    with open(GOOGLE_ADS_YAML_FILE, 'w') as f:
        yaml.dump(config, f)
    print("Updated credentials in google-ads.yaml.")

if __name__ == "__main__":
    # Get credentials
    credentials = get_credentials()

    # Example usage: Update google-ads.yaml with obtained credentials
    if credentials:
        update_google_ads_yaml(credentials.client_id, credentials.client_secret, credentials.refresh_token)
        # Print refresh token for verification
        print("Refresh Token:", credentials.refresh_token)
    else:
        print("Failed to retrieve credentials.")

    try:
        # Initialize client object.
        client = GoogleAdsClient.load_from_storage("google-ads.yaml")

        # Replace with your Google Ads customer ID.
        customer_id = os.getenv('CUSTOMER_ID')

        # Define the name for the custom audience segment
        audience_name = "test result emails"

        # Get or create the custom audience segment
        user_list_resource_name = get_or_create_custom_audience(client, customer_id, audience_name)

        if user_list_resource_name:
            # Path to the CSV file containing user data
            csv_file_path = "emails1000.csv"

            # Upload CSV data to the custom audience segment
            upload_csv_to_custom_audience(client, customer_id, user_list_resource_name, csv_file_path)

    except GoogleAdsException as ex:
        print(f"Google Ads API request failed. Details: {ex}")
    except Exception as e:
        print(f"An error occurred: {e}")