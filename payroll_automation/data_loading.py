import pandas as pd
import os
from glob import glob
from zipfile import BadZipFile

# Data Loading functions
def read_excel_safe(file_path, usecols):
    if not os.path.exists(file_path):
        print(f"File does not exist: {file_path}")
        return pd.DataFrame()
    
    if not os.access(file_path, os.R_OK):
        print(f"File is not readable: {file_path}")
        return pd.DataFrame()
    
    try:
        return pd.read_excel(file_path, usecols=usecols, engine='openpyxl')
    except BadZipFile:
        print(f"File is not a valid Excel file or is corrupted: {file_path}")
        return pd.DataFrame()
    except ValueError as e:
        print(f"Error reading {file_path}: {str(e)}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Unexpected error reading {file_path}: {str(e)}")
        return pd.DataFrame()

def load_timesheets(directory):
    all_timesheets = []

    timesheet_files = glob(os.path.join(directory, '*Timesheet*.xlsx'))

    for file in timesheet_files:
        if 'Temp' in file:
            df = process_temp_timesheet(file)
        else:
            df = process_timesheet(file)
        if not df.empty:
            all_timesheets.append(df)

    combined_timesheet = pd.concat(all_timesheets, ignore_index=True) if all_timesheets else pd.DataFrame()

    return combined_timesheet


def load_schedules(directory):
    all_schedules = []
    # Use a list comprehension to get both types of files
    schedule_files = [
        file for pattern in ['*Schedule-Export*.xlsx', '*Shift*.xlsx']
        for file in glob(os.path.join(directory, pattern))
    ]
    
    for file in schedule_files:
        print(f"Processing schedule file: {file}")  # For debugging
        df = process_schedule(file)
        if not df.empty:
            # Add a column to indicate the source file type
            df['Source'] = 'Schedule-Export' if 'Schedule-Export' in file else 'Shift'
            all_schedules.append(df)
    
    if all_schedules:
        combined_schedule = pd.concat(all_schedules, ignore_index=True)
        print(f"Total schedules loaded: {len(all_schedules)}")  # For debugging
        print(f"Combined schedule shape: {combined_schedule.shape}")  # For debugging
    else:
        combined_schedule = pd.DataFrame()
        print("No schedules found or loaded.")  # For debugging
    
    return combined_schedule

def load_public_holidays(start_date):
    print("\nLoading Public Holidays")
    
    # Extract year from start_date
    year = int(start_date[:4])
    print(f"Generating holidays for the year: {year}")

    # Create a Canada holidays object
    ca_holidays = holidays.CA(years=year, prov='ON')  # Using Ontario for Civic Holiday

    # List of holidays we want to include
    holiday_names = [
        "New Year's Day",
        "Family Day",
        "Good Friday",
        "Victoria Day",
        "Canada Day",
        "Civic Holiday",
        "Labour Day",
        "Thanksgiving",
        "Christmas Day",
        "Boxing Day"
    ]

    # Filter and create the holidays DataFrame
    holiday_list = []
    for date, name in ca_holidays.items():
        if any(holiday in name for holiday in holiday_names):
            holiday_list.append({'Date': date, 'Description': name})

    # Create DataFrame and sort by date
    holidays_df = pd.DataFrame(holiday_list)
    holidays_df = holidays_df.sort_values('Date').reset_index(drop=True)

    # Ensure 'Date' column is datetime
    holidays_df['Date'] = pd.to_datetime(holidays_df['Date'])

    print(f"Generated {len(holidays_df)} holidays for {year}")
    return holidays_df

def load_production_report(directory):
    print("\nLoading Production Report")
    production_files = glob(os.path.join(directory, '*Production Report*.xlsx'))
    if not production_files:
        print("No Production Report found.")
        return pd.DataFrame()

    df = pd.read_excel(production_files[0])
    df = df[['Date', 'Employee ID', 'Silver Bonus', 'Gold Bonus']]
    
    # Fill null values with 0
    df['Silver Bonus'] = df['Silver Bonus'].fillna(0)
    df['Gold Bonus'] = df['Gold Bonus'].fillna(0)
    
    df['Bonus'] = df['Silver Bonus'] + df['Gold Bonus']
    df = df.groupby(['Date', 'Employee ID'])['Bonus'].sum().reset_index()
    return df

def load_payrate_list(file_path):
    print("\nLoading Employee PayRate List")
    df = pd.read_excel(file_path)
    print("Columns in Employee PayRate List:")
    print(df.columns.tolist())
    
    # Replace empty strings with NaN
    df = df.replace(r'^\s*$', np.nan, regex=True)
    
    # Check if 'Employee ID' column exists, if not, try to find a similar column
    if 'Employee ID' not in df.columns:
        possible_id_columns = [col for col in df.columns if 'id' in col.lower() or 'number' in col.lower()]
        if possible_id_columns:
            print(f"'Employee ID' column not found. Using '{possible_id_columns[0]}' as the Employee ID column.")
            df = df.rename(columns={possible_id_columns[0]: 'Employee ID'})
        else:
            print("Warning: No column found that could be used as 'Employee ID'.")
    
    return df
