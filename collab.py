import os
import string
import logging
import threading
import subprocess
import json
import time
import re
import unicodedata
from django.shortcuts import render
from django.conf import settings

# Get the logger for the binblock app
logger = logging.getLogger('binblock')

# Define the output directory
OUTPUT_DIR = os.path.join(settings.BASE_DIR, 'binblock', 'output')

def run_sqlplus_command(command, query, output_file, server_name):
    """Run SQL*Plus command and capture the output."""
    logger.debug(f"Running SQL*Plus command on {server_name} with query: {query}")
    
    start_time = time.time()  # Start timing
    
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    stdout, stderr = process.communicate(input=query.encode())
    
    end_time = time.time()  # End timing
    
    # Calculate time taken
    elapsed_time = end_time - start_time
    logger.info(f"SQL*Plus command on {server_name} completed in {elapsed_time:.2f} seconds.")

    if process.returncode != 0:
        logger.error(f"SQL*Plus command failed on {server_name}: {stderr.decode()}")
        raise Exception(f"SQL*Plus command failed on {server_name}: {stderr.decode()}")

    output_lines = [line for line in stdout.decode().splitlines() if line.strip()]
    with open(output_file, "w") as file:
        file.write("\n".join(output_lines) + "\n")
    
    logger.debug(f"SQL*Plus command completed on {server_name}. Output written to {output_file}")

def clean_file(file_path):
    """Clean the output file by removing unnecessary lines."""
    with open(file_path, 'r') as file:
        lines = file.readlines()

    # Find indexes for relevant content
    start_index = next((i for i, line in enumerate(lines) if 'SQL>' in line), 0) + 1
    end_index = next((i for i in range(len(lines) - 1, -1, -1) if 'SQL>' in lines[i]), len(lines))

    # Clean lines between indexes
    cleaned_lines = [
        ''.join(char for char in line if char in string.printable).strip()
        for line in lines[start_index:end_index]
        if 'rows selected' not in line.lower() and not line.strip().startswith('-') and line.strip() != 'JSON_DATA'
    ]

    with open(file_path, 'w') as file:
        file.write("\n".join(cleaned_lines) + "\n")

def clean_distinct_file(file_path):
    """Clean the distinct output file and return as a list of cleaned items."""
    logger.debug(f"Cleaning output file for distinct query: {file_path}")
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()

        # Find the start and end indices for relevant content
        start_index = next((i for i, line in enumerate(lines) if 'SQL>' in line), 0) + 1
        end_index = next((i for i in range(len(lines) - 1, -1, -1) if 'SQL>' in lines[i]), len(lines))

        # Clean lines between the determined indices
        cleaned_list = []
        for line in lines[start_index:end_index]:
            line = ''.join(char for char in line if char in string.printable).strip()

            if not line or 'rows selected' in line.lower():
                continue

            if line.startswith('-') or line == 'DESCRIPTION':
                continue

            cleaned_list.append(line)

        logger.info(f"Successfully cleaned distinct output file: {file_path} with {len(cleaned_list)} entries")
        return cleaned_list

    except Exception as e:
        logger.error(f"Error cleaning distinct output file {file_path}: {e}")
        return []

def categorize_and_expand_items(distinct_list, search_items=None):
    """Categorize 'RUSSIAN' and 'SYRIA' variations into single categories for blocking and expand them for search items if needed."""
    categorized_list = []
    expanded_items = []

    for item in distinct_list:
        if item.startswith("RUSSIAN"):
            if "RUSSIAN" not in categorized_list:
                categorized_list.append("RUSSIAN")
        elif item.startswith("SYRIA"):
            if "SYRIA" not in categorized_list:
                categorized_list.append("SYRIA")
        else:
            categorized_list.append(item)

    if search_items:
        for item in search_items:
            if item in ["RUSSIAN", "SYRIA"]:
                expanded_items.extend([i for i in distinct_list if i.startswith(item)])
            else:
                expanded_items.append(item)

    return categorized_list, expanded_items

def remove_control_characters(text):
    """Remove all control characters and normalize the text."""
    # Normalize the text to NFKD form
    normalized_text = unicodedata.normalize('NFKD', text)
    
    # Remove control characters except printable ones
    cleaned_text = ''.join(c for c in normalized_text if c.isprintable())
    
    # Further remove specific unwanted characters like tabs, newlines, etc.
    cleaned_text = re.sub(r'[\x00-\x1F\x7F]', '', cleaned_text)
    
    return cleaned_text

def remove_null_values(d):
    """Recursively remove null values from dictionaries and lists."""
    logger.debug("Starting remove_null_values")
    if isinstance(d, dict):
        cleaned_data = {k: remove_null_values(v) for k, v in d.items() if v is not None}
    elif isinstance(d, list):
        cleaned_data = [remove_null_values(v) for v in d if v is not None]
    else:
        cleaned_data = d
    logger.debug("Completed remove_null_values")
    return cleaned_data

def apply_length_checks(json_obj):
    """Apply length checks to JSON fields based on configuration."""
    length_config = {
        "LOWBIN": {"type": "CHAR", "length": 15},
        "HIGHBIN": {"type": "CHAR", "length": 15},
        "O_LEVEL": {"type": "NUMBER", "length": 1},
        "STATUS": {"type": "CHAR", "length": 1},
        "DESCRIPTION": {"type": "CHAR", "length": 50},
        "DESTINATION": {"type": "CHAR", "length": 3},
        "ENTITY_ID": {"type": "CHAR", "length": 1},
        "CARDPRODUCT": {"type": "CHAR", "length": 20},
        "NETWORK_DATA": {"type": "CHAR", "length": 10},
        "FILE_NAME": {"type": "CHAR", "length": 10},
        "FILE_VERSION": {"type": "CHAR", "length": 5},
        "FILE_DATE": {"type": "DATE", "length": None},
        "COUNTRY_CODE": {"type": "CHAR", "length": 3},
        "NETWORK_CONFIG": {"type": "CHAR", "length": 10},
        "BIN_LENGTH": {"type": "NUMBER", "length": 2}
    }

    for key, value in json_obj.items():
        if key in length_config:
            config = length_config[key]
            if config["type"] == "CHAR" and config["length"] is not None:
                json_obj[key] = str(value).ljust(config["length"])[:config["length"]]
            elif config["type"] == "NUMBER" and config["length"] is not None:
                json_obj[key] = str(value).zfill(config["length"])[:config["length"]]
    return json_obj

def json_to_sql_insert(json_obj, table_name):
    """Convert a JSON object to an SQL INSERT statement for a specified table."""
    logger.debug("Starting json_to_sql_insert")
    keys = list(json_obj.keys())
    values = [
        f"TO_DATE('{value.strip()}', 'DD/MM/YYYY')" if key == "FILE_DATE" and value else 
        str(value) if key == "O_LEVEL" else 
        f"'{value}'" if isinstance(value, str) else str(value) 
        for key, value in json_obj.items()
    ]
    sql_statement = f"INSERT INTO {table_name} ({', '.join(keys)}) VALUES ({', '.join(values)});"
    logger.debug("Completed json_to_sql_insert")
    return sql_statement

def convert_to_sql_insert_statements(json_list, table_name):
    """Convert a list of cleaned JSON objects to SQL INSERT statements."""
    logger.debug("Starting convert_to_sql_insert_statements")
    statements = [json_to_sql_insert(entry, table_name) for entry in json_list]
    logger.debug("Completed convert_to_sql_insert_statements")
    return statements

def save_sql_statements_to_file(statements, file_path):
    """Save SQL INSERT statements to a file."""
    logger.debug(f"Starting save_sql_statements_to_file for {file_path}")
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write("\n".join(statements))
        logger.info(f"SQL statements saved to {file_path}")
    except Exception as e:
        logger.error(f"Error saving SQL statements to file {file_path}: {e}")
    logger.debug(f"Completed save_sql_statements_to_file for {file_path}")

def preprocess_json_file(file_path, table_name, output_sql_file):
    """Preprocess the JSON file to remove unwanted control characters, format it properly, remove null values, apply length checks, and save as SQL insert statements."""
    logger.debug(f"Starting preprocess_json_file for file: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        # Remove control characters from each line and strip whitespace
        cleaned_lines = [remove_control_characters(line.strip()) for line in lines if line.strip()]

        # Join the cleaned lines together into a single string
        json_data = ''.join(cleaned_lines)

        # Add commas only between adjacent JSON objects by finding '}{' and replacing it with '},{'
        json_data = re.sub(r'\}\s*\{', '},{', json_data)

        # Wrap in brackets to make it a valid JSON array
        json_data = f"[{json_data}]"

        # Convert the cleaned string back to a Python object
        try:
            json_object = json.loads(json_data)
        except json.JSONDecodeError as e:
            logger.error(f"Error loading JSON data: {e}")
            raise

        # Remove null values from JSON data
        cleaned_json_object = [remove_null_values(obj) for obj in json_object]

        # Apply length checks to each JSON object
        checked_json_object = [apply_length_checks(obj) for obj in cleaned_json_object]

        # Reformat JSON data with indentation for readability
        formatted_json = json.dumps(checked_json_object, indent=4)

        # Write the formatted JSON data back to the file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(formatted_json)

        # Convert the cleaned JSON objects to SQL insert statements
        sql_statements = convert_to_sql_insert_statements(checked_json_object, table_name)

        # Save the SQL statements to the output file
        save_sql_statements_to_file(sql_statements, output_sql_file)

        logger.debug(f"Completed preprocess_json_file for file: {file_path}")

    except Exception as e:
        logger.error(f"Error preprocessing JSON file {file_path}: {e}")

def run_background_queries():
    """Run prod and uat queries in the background, clean the output files, and perform further processing."""
    logger.debug("Starting background queries for prod and uat")

    def run_query_and_process(command, query, output_file, server_name):
        try:
            logger.debug(f"Running query for {server_name}")
            run_sqlplus_command(command, query, output_file, server_name)
            
            cleaned_data = clean_file(output_file)
            logger.info(f"Cleaned data from {server_name}: {cleaned_data}")

            preprocess_json_file(output_file, 'your_table_name', os.path.join(OUTPUT_DIR, f"{server_name.lower()}_insert_statements.sql"))

        except Exception as e:
            logger.error(f"Error running SQL query or processing data on {server_name}: {e}")

    prod_command = "sqlplus oasis77/ist0py@istu2"
    uat_command = "sqlplus oasis77/ist0py@istu2"
    query = "SELECT JSON_OBJECT(*) AS JSON_DATA FROM (SELECT * FROM oasis77.SHCEXTBINDB ORDER BY LOWBIN) WHERE ROWNUM <= 4;"
    prod_output_file = os.path.join(OUTPUT_DIR, 'prod_output.json')
    uat_output_file = os.path.join(OUTPUT_DIR, 'uat_output.json')

    threading.Thread(target=run_query_and_process, args=(prod_command, query, prod_output_file, "Prod")).start()
    threading.Thread(target=run_query_and_process, args=(uat_command, query, uat_output_file, "UAT")).start()

def bin_blocking_editor(request):
    logger.info("Bin blocking editor view accessed")
    result = None
    log_with_delays = None
    prod_distinct_list = []

    try:
        distinct_command = "sqlplus oasis77/ist0py@istu2"
        distinct_query = "SELECT DISTINCT description FROM oasis77.SHCEXTBINDB ORDER BY DESCRIPTION;"
        distinct_output_file = os.path.join(OUTPUT_DIR, 'prod_distinct_output.txt')
        run_sqlplus_command(distinct_command, distinct_query, distinct_output_file, "Distinct")

        # Use clean_distinct_file to clean the distinct query output
        prod_distinct_list = clean_distinct_file(distinct_output_file)
        categorized_list, _ = categorize_and_expand_items(prod_distinct_list)

        # Run prod and uat queries in the background
        run_background_queries()

    except Exception as e:
        logger.error(f"Error running distinct query: {e}")
        categorized_list = []

    if request.method == 'POST':
        blocked_item = request.POST.get('blocked_item')
        search_items = request.POST.getlist('search_items')

        _, expanded_search_items = categorize_and_expand_items(prod_distinct_list, search_items)
        logger.info(f"User selected blocked item: {blocked_item} and expanded search items: {expanded_search_items}")

    context = {
        'result': result,
        'log_with_delays': log_with_delays,
        'prod_distinct_list': categorized_list
    }
    logger.info("Rendering binblocker.html with context data")
    return render(request, 'binblock/binblocker.html', context)
