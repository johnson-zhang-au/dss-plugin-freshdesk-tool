from dataiku.customrecipe import get_output_names_for_role
from dataiku.customrecipe import get_recipe_config
from datetime import datetime
import logging
import dataiku
import pandas as pd
import requests
import base64
import os

config = get_recipe_config()

# Set up logging
logging_level = config.get('logging_level', "INFO")

# Map string levels to logging constants
level_mapping = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

level = level_mapping.get(logging_level, logging.INFO)  # Default to INFO if not found

logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')

# Set up the logger with the script name
script_name = os.path.basename(__file__).split('.')[0]
logger = logging.getLogger(script_name)
logger.setLevel(level)

logger.info("Starting the Freshdesk tickets fetcher recipe.")
logger.debug(f"Configuration loaded: {config}")


def create_auth_headers(api_key):
    """
    Creates the authentication headers for Freshdesk API requests.

    Args:
        api_key (str): Freshdesk API key.

    Returns:
        dict: A dictionary containing the authentication headers.
    """
    auth_string = f"{api_key}:X"
    auth_bytes = auth_string.encode('ascii')
    base64_auth = base64.b64encode(auth_bytes).decode('ascii')

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {base64_auth}"
    }
    return headers


def fetch_tickets(api_key, domain, ticket_statuses):
    """
    Fetches tickets from Freshdesk using the search API.

    Args:
        api_key (str): Freshdesk API key.
        domain (str): Freshdesk domain.
        ticket_statuses (list): List of ticket statuses to filter by.

    Returns:
        list: A list of tickets.
    """
    logger.info("Fetching tickets from Freshdesk.")
    base_url = f"https://{domain}/api/v2/search/tickets"
    headers = create_auth_headers(api_key)

    # Build the query for ticket statuses
    if ticket_statuses:
        status_query = " OR ".join([f"status:{status}" for status in ticket_statuses])
        query = f"query=\"{status_query}\""
    else:
        query = "query=\"\""

    url = f"{base_url}?{query}"
    logger.debug(f"Constructed URL: {url}")
    all_tickets = []

    page = 1
    while True:
        paginated_url = f"{url}&page={page}"
        logger.debug(f"Fetching page {page} with URL: {paginated_url}")
        response = requests.get(paginated_url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Append tickets from the current page
        tickets = data.get("results", [])
        logger.info(f"Fetched {len(tickets)} tickets from page {page}.")
        all_tickets.extend(tickets)

        # Check if there are more pages
        if not tickets:
            logger.info("No more pages to fetch.")
            break
        page += 1

    logger.info(f"Total tickets fetched: {len(all_tickets)}")
    return all_tickets


def fetch_conversations(api_key, domain, tickets):
    """
    Fetches conversations for each ticket and adds them to the ticket data.

    Args:
        api_key (str): Freshdesk API key.
        domain (str): Freshdesk domain.
        tickets (list): List of tickets.

    Returns:
        list: A list of tickets with filtered conversations added.
    """
    logger.info("Fetching conversations for tickets.")
    headers = create_auth_headers(api_key)

    for ticket in tickets:
        ticket_id = ticket.get("id")
        if ticket_id:
            conversations_url = f"https://{domain}/api/v2/tickets/{ticket_id}/conversations"
            logger.debug(f"Fetching conversations for ticket ID {ticket_id} with URL: {conversations_url}")
            try:
                response = requests.get(conversations_url, headers=headers)
                response.raise_for_status()
                conversations = response.json()

                # Filter conversations to only keep specified keys
                filtered_conversations = [
                    {
                        "body_text": conv.get("body_text"),
                        "id": conv.get("id"),
                        "updated_at": conv.get("updated_at"),
                        "from_email": conv.get("from_email"),
                    }
                    for conv in conversations
                ]
                ticket["conversations"] = filtered_conversations
            except requests.exceptions.RequestException as e:
                logger.error(f"Error retrieving conversations for ticket ID {ticket_id}: {e}")
                ticket["conversations"] = []

    return tickets


def get_tickets_as_dataframe(api_key, domain, ticket_statuses):
    """
    Retrieves tickets and their conversations from Freshdesk and stores them in a pandas DataFrame.

    Args:
        api_key (str): Freshdesk API key.
        domain (str): Freshdesk domain.
        ticket_statuses (list): List of ticket statuses to filter by.

    Returns:
        pd.DataFrame: A DataFrame containing ticket details and conversations.
    """
    tickets = fetch_tickets(api_key, domain, ticket_statuses)
    tickets_with_conversations = fetch_conversations(api_key, domain, tickets)
    return pd.DataFrame(tickets_with_conversations)


# Retrieve configuration parameters
api_key = config["freshdesk_api_connection"]["apiKey"]
domain = config["freshdesk_api_connection"]["freshdesk_domain"]
ticket_statuses = config["ticket_statuses"]

logger.info("Starting ticket retrieval process.")
df = get_tickets_as_dataframe(api_key, domain, ticket_statuses)

# Get the output dataset
output_name = get_output_names_for_role('data_output')[0]
output_dataset = dataiku.Dataset(output_name)

logger.info(f"Writing tickets to output dataset: {output_name}")
# Write to the output dataset
output_dataset.write_with_schema(df)
logger.info("Tickets successfully written to the output dataset.")