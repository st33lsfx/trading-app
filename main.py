import os
from dotenv import load_dotenv
from client import Trading212Client

# Load environment variables
load_dotenv()

API_KEY = os.getenv("T212_API_KEY")
BASE_URL = os.getenv("T212_BASE_URL")

def main():
    if not API_KEY:
        print("Error: API Key not found in .env file.")
        return

    print(f"Connecting to Trading 212 ({BASE_URL})...")
    client = Trading212Client(API_KEY, BASE_URL)

    try:
        # Fetch account cash to verify connection
        cash = client.get_account_cash()
        print("\nAccount Cash:")
        print(cash)
        
        # Fetch summary
        # summary = client.get_account_summary()
        # print("\nAccount Summary:")
        # print(summary)

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
