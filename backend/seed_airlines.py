#!/usr/bin/env python3
"""
Quick script to seed the airlines table with test data.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from auth import _get_supabase_client


def main():
    test_airlines = [
        {"code": "GA", "name": "Garuda Indonesia"},
        {"code": "SQ", "name": "Singapore Airlines"},
        {"code": "MH", "name": "Malaysia Airlines"},
        {"code": "EK", "name": "Emirates"},
        {"code": "QF", "name": "Qantas"},
    ]

    db = _get_supabase_client()
    for airline in test_airlines:
        try:
            response = db.table("airlines").insert(airline).execute()
            print(f"Inserted: {airline}")
        except Exception as e:
            print(f"Error inserting {airline}: {e}")

    print("Done!")


if __name__ == "__main__":
    main()
