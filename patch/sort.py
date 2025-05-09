import csv
import pandas as pd


# First, write all your data to the CSV file as you normally would
# ...your existing code that creates the CSV...

# Then, remove duplicates after the file is created
def deduplicate_csv(filename):
    # Read the CSV into a pandas DataFrame
    df = pd.read_csv(filename)

    # Remove duplicate rows
    df_no_duplicates = df.drop_duplicates()

    # Write back to the same file (or a new one if you prefer)
    df_no_duplicates.to_csv(filename, index=False)


# Usage
deduplicate_csv('your_output_file.csv')

import json


# First, write all your data to the JSON file as you normally would
# ...your existing code that creates the JSON...

# Then, remove duplicates
def deduplicate_json(filename):
    # Read the JSON file
    with open(filename, 'r') as f:
        data = json.load(f)

    # If data is a list of dictionaries
    if isinstance(data, list):
        # Convert dictionaries to tuples of items (for hashability)
        seen = set()
        new_data = []

        for item in data:
            # Convert dict to a hashable representation
            item_tuple = tuple(sorted(item.items()))

            if item_tuple not in seen:
                seen.add(item_tuple)
                new_data.append(item)

        # Write the deduplicated data back
        with open(filename, 'w') as f:
            json.dump(new_data, f, indent=2)


# Usage
deduplicate_json('your_output_file.json')