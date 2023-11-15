import os
import math
import numpy as np 
import pandas as pd 
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages

import warnings
warnings.filterwarnings('ignore')

# UDFs
## Data Loader
# Functions for clean time sheet
def find_files(input_path):
    # Dictionary to store the output paths
    output_paths = {
        "Time_Sheet_Path": [],
        "Sheeting_Operator_Report_Path": [],
        "Die_Price_df_Path": [],
        "Other_Operator_Report_Path": [],
        "Production_Report_Path": [],
        "Operator_Bonus_Rate_Path": []
    }

    # Iterate over the files in the input path
    for root, dirs, files in os.walk(input_path):
        for file in files:
            # Convert the file name to lowercase for case-insensitive comparison
            file_lower = file.lower()
            file_path = os.path.join(root, file)

            # Check the file name and update the corresponding path in the dictionary
            if "timesheet" in file_lower:
                output_paths["Time_Sheet_Path"].append(file_path)
            elif "sheeting" in file_lower:
                output_paths["Sheeting_Operator_Report_Path"].append(file_path)
            elif "die" in file_lower:
                output_paths["Die_Price_df_Path"].append(file_path)
            elif "other" in file_lower:
                output_paths["Other_Operator_Report_Path"].append(file_path)
            elif "production" in file_lower:
                output_paths["Production_Report_Path"].append(file_path)
            elif "bonus" in file_lower:
                output_paths["Operator_Bonus_Rate_Path"].append(file_path)

    return output_paths

def load_and_process_data(paths, processing_function, skiprows=None):
    dfs = []  # List to store individual DataFrames
    for path in paths:
        df = pd.read_excel(path, skiprows=skiprows, engine='openpyxl')
        dfs.append(processing_function(df))
    
    # Concatenate all DataFrames in the list
    combined_df = pd.concat(dfs, ignore_index=True)
    return combined_df

def process_sheeting_data(df):
    # df = pd.read_excel(path)
    df = df.dropna(subset=['Paper number (sheet)'])
    df['Date of filling'] = pd.to_datetime(df['Date of filling'])
    df['Start time'] = pd.to_datetime(df['Start time'])
    df['End time'] = pd.to_datetime(df['End time'])
    df['Employee number'] = df['Employee number'].astype(str)
    df['Paper number (sheet)'] = pd.to_numeric(df['Paper number (sheet)'], errors='coerce')
    return df

def process_time_sheet_data(df): 
    pass
    return combined_df

def process_die_price_data(df):
    df = df[['ERPNum','ProductID','Price']]

    # Splitting the 'ERPNum' column and exploding it into separate rows
    df['ERPNum'] = df['ERPNum'].str.split(',')
    df = df.explode('ERPNum').reset_index(drop=True)
    return df

def process_other_process_data(df):
    # Convert columns to appropriate data types
    df['Actual shift date'] = pd.to_datetime(df['Actual shift date'])

    # Select the columns you need
    df = df[['ERPNum','Product','Main product code', 'Makeup Style','Process', 'DeviceName', 'Die Number', 'Actual shift date', 'Member ID', 'Output Qty']]

    df = df.dropna(subset=['Member ID'])

    # Convert 'Order Qty' and 'Output Qty' to numbers
    df['Output Qty'] = pd.to_numeric(df['Output Qty'], errors='coerce')

    # Cleaning up the 'Main product code' column
    df['Main product code'] = df['Main product code'].str.split('|').str[0]
    return df

def process_bonus_rate_data(df):
    df = df[['Payroll NO.','Name','Location','Machine','Silver Rate', 'Gold Rate']].rename(columns={'Payroll NO.': 'Employee number'})
    df = clean_and_rename_columns(df)
    return df

def adjust_start_time(dt):
    # Adjust start datetime
    if dt.minute >= 0 and dt.minute <= 5:
        return dt.replace(minute=0)
    elif dt.minute >= 6 and dt.minute <= 35:
        return dt.replace(minute=30)
    else:
        return (dt + pd.Timedelta(hours=1)).replace(minute=0)

def adjust_end_time(dt):
    # Adjust end datetime
    if dt.minute >= 0 and dt.minute <= 24:
        return dt.replace(minute=0)
    elif dt.minute >= 25 and dt.minute <= 54:
        return dt.replace(minute=30)
    else:
        return (dt + pd.Timedelta(hours=1)).replace(minute=0)

def combine_time(df):
    # Combine start date and start time into start datetime
    df['Start Datetime'] = pd.to_datetime(df['Start Date'] + ' ' + df['Start time'], format='%d/%m/%Y %H:%M')

    # Combine end date and end time into end datetime
    df['End Datetime'] = pd.to_datetime(df['End Date'] + ' ' + df['End time'], format='%d/%m/%Y %H:%M')
    
    # Adjust start and end times
    df['Adjusted Start Datetime'] = df['Start Datetime'].apply(adjust_start_time)
    df['Adjusted End Datetime'] = df['End Datetime'].apply(adjust_end_time)
    
    # Calculate working hours
    df['Working Hours'] = (df['Adjusted End Datetime'] - df['Adjusted Start Datetime']).dt.total_seconds() / 3600

    # Sort the dataframe by 'Employee Number' and 'Start Datetime'
    df = df.sort_values(by=['Employee Number', 'Start Datetime']).reset_index(drop=True)

    # Identify rows where the end time is 00:00 and the start time of the next record is also 00:00
    end_at_midnight = (df['End Datetime'].dt.hour == 0) & (df['End Datetime'].dt.minute == 0)
    start_at_midnight = (df['Start Datetime'].dt.hour == 0) & (df['Start Datetime'].dt.minute == 0)

    # Shift the 'Employee Number', 'End Datetime', and 'Working Hours' columns to identify pairs of records for the same employee
    df['Next Employee Number'] = df['Employee Number'].shift(-1)
    df['Next Working Hours'] = df['Working Hours'].shift(-1)

    # Identify rows to be combined
    combine_rows = end_at_midnight & start_at_midnight.shift(-1) & (df['Employee Number'] == df['Next Employee Number'])

    # Combine the records by summing the working hours
    df.loc[combine_rows, 'Working Hours'] += df.loc[combine_rows, 'Next Working Hours']
    
    # Keep rows that are not the second part of a combined pair
    df_to_keep = ~(combine_rows.shift(1, fill_value=False) & (df['Employee Number'] == df['Employee Number'].shift(1)))

    # Filter the dataframe
    df = df[df_to_keep].reset_index(drop=True)

    # Drop the temporary columns
    df = df.drop(columns=['Next Employee Number', 'Next Working Hours'])

    return df

def process_time_sheet_data(Time_Sheet_df):
    """
    Processes the Time_Sheet_df to calculate working hours and adjust start and end times.

    Parameters:
    - Time_Sheet_df: DataFrame containing the time sheet data.
    - combine_time: Function to handle the scenario where an employee's end time on one day is close to midnight and their start time on the next day is shortly after midnight.
    - adjust_start_time: Function to adjust the start time.
    - adjust_end_time: Function to adjust the end time.

    Returns:
    - Processed Time_Sheet_df.
    """

    # Handle the scenario where an employee's end time on one day is close to midnight and their start time on the next day is shortly after midnight
    Time_Sheet_df = combine_time(Time_Sheet_df)

    # Adjust start and end times
    Time_Sheet_df['Adjusted Start Datetime'] = Time_Sheet_df['Start Datetime'].apply(adjust_start_time)
    Time_Sheet_df['Adjusted End Datetime'] = Time_Sheet_df['End Datetime'].apply(adjust_end_time)

    # Drop rows where 'Working Hours' is null or 0
    Time_Sheet_df = Time_Sheet_df[Time_Sheet_df['Working Hours'].notna() & (Time_Sheet_df['Working Hours'] != 0)]

    Time_Sheet_df = Time_Sheet_df.drop(columns=['Start time','End Date','End time','Start Datetime','End Datetime','Adjusted Start Datetime','Adjusted End Datetime'])
    Time_Sheet_df['Start Date'] = pd.to_datetime(Time_Sheet_df['Start Date'], format='%d/%m/%Y').dt.strftime('%Y-%m-%d')

    return Time_Sheet_df


def clean_and_rename_columns(df):
    """
    Cleans and renames all column names in a DataFrame.
    
    Steps:
    1. Remove spaces at the beginning and end of the column name.
    2. Capitalize the first letter of each word.
    3. Remove underscores (_) and hyphens (-).
    
    Parameters:
    - df: DataFrame to be processed.
    
    Returns:
    - DataFrame with cleaned and renamed columns.
    """
    
    def format_column_name(col_name):
        # Remove spaces at the beginning and end
        col_name = col_name.strip()
        # Capitalize the first letter of each word
        col_name = ' '.join([word.capitalize() for word in col_name.split()])
        # Remove underscores and hyphens
        col_name = col_name.replace("_", "").replace("-", "")
        return col_name
    
    # Apply the format_column_name function to each column name
    df.columns = [format_column_name(col) for col in df.columns]
    
    return df

## Calculation for Sheeting
# Calculation for Sheeting

def process_and_merge_data(sheeting_df, Time_Sheet_df, Operator_Bonus_Rate_df, 
                           clean_and_rename_columns, flag_gold_sheeting, calculate_gold_bonus):
    # Extract and convert 'Start Date' from 'Start time' in sheeting_df
    sheeting_df['Start Date'] = pd.to_datetime(sheeting_df['Start time'].dt.date)
    
    # Ensure 'Start Date' in Time_Sheet_df is datetime type and clean/rename columns
    Time_Sheet_df['Start Date'] = pd.to_datetime(Time_Sheet_df['Start Date'])
    Time_Sheet_df = clean_and_rename_columns(Time_Sheet_df)
    
    # Group by 'Employee number' and 'Start Date', then sum 'Paper number (sheet)'
    sheeting_df = sheeting_df.groupby(['Employee number', 'Start Date'])['Paper number (sheet)'].sum().reset_index()
    sheeting_df = clean_and_rename_columns(sheeting_df)
    
    # Merge DataFrames and filter Operator_Bonus_Rate_df
    merged_sheeting_df = pd.merge(Time_Sheet_df, sheeting_df,
                                  left_on=['Employee Number', 'Start Date'],
                                  right_on=['Employee Number', 'Start Date'],
                                  how='inner')
    sheeter_rate_df = Operator_Bonus_Rate_df[Operator_Bonus_Rate_df['Machine'] == 'Sheeter']
    merged_sheeting_df = pd.merge(merged_sheeting_df, sheeter_rate_df,
                                  on='Employee Number',
                                  how='left')
    
    # Apply functions to create 'Gold' and 'Gold Bonus' columns
    merged_sheeting_df['Gold'] = merged_sheeting_df.apply(flag_gold_sheeting, axis=1)
    merged_sheeting_df['Gold Bonus'] = merged_sheeting_df.apply(calculate_gold_bonus, axis=1)
    merged_sheeting_df = merged_sheeting_df.drop_duplicates()
    
    # Filter rows where 'Gold' is True and create 'flag_not_report_working_hour' column
    # merged_sheeting_df = merged_sheeting_df[merged_sheeting_df['Gold'] == True]
    merged_sheeting_df['flag_not_report_working_hour'] = np.where(
        (merged_sheeting_df['Paper Number (sheet)'] > 0) & merged_sheeting_df['Working Hours'].isna(), 
        'yes', 
        'no'
    )
    
    return merged_sheeting_df

## Calculation for other process
# Calculation for other process
def process_and_calculate_revenue(other_df, Die_Price_df, Time_Sheet_df, Operator_Bonus_Rate_df, 
                                  make_ready_count, silver_eligibility, gold_eligibility):
    
    # Merge and calculate 'Revenue'
    other_df = pd.merge(other_df, Die_Price_df, how='left', 
                        left_on=['ERPNum', 'Main product code'], 
                        right_on=['ERPNum', 'ProductID'])
    other_df['Output Qty'] = pd.to_numeric(other_df['Output Qty'], errors='coerce')
    other_df['Revenue'] = (other_df['Output Qty'] * other_df['Price'])
    
    # Update 'Process' column
    def update_process(row):
        if row['Process'] == 'Printing' and row['DeviceName'] == 'SP1-HD102CX':
            return 'Printing_CX102'
        elif row['Process'] == 'Printing' and row['DeviceName'] == 'CP1-HD104CX':
            return 'Printing_CX104'
        else:
            return row['Process']
    other_df['Process'] = other_df.apply(update_process, axis=1)
    
    # Calculate 'MakeReady' and 'Number of Lines'
    other_df['MakeReady'] = other_df.groupby(['Product', 'Process', 'DeviceName', 'Die Number', 'Actual shift date', 'Member ID']).apply(make_ready_count).reset_index(drop=True)
    other_df['Number of Lines'] = other_df.groupby(['Member ID', 'Process', 'Actual shift date'])['DeviceName'].transform('nunique')
    
    # Group and aggregate data
    other_df = other_df.groupby(['Process', 'Actual shift date', 'Member ID'])[['Output Qty', 'MakeReady', 'Number of Lines', 'Revenue']].agg({'Output Qty': 'sum', 'MakeReady': 'sum', 'Number of Lines': 'max', 'Revenue': 'sum'}).reset_index()
    
    # Merge DataFrames
    merged_other_df = pd.merge(Time_Sheet_df, other_df,
                               left_on=['Employee Number', 'Start Date'],
                               right_on=['Member ID', 'Actual shift date'],
                               how='right')
    merged_other_df = pd.merge(merged_other_df, Operator_Bonus_Rate_df,
                               on='Employee Number',
                               how='left')
    
    # Create new columns and fill NaN values
    merged_other_df['flag_not_report_working_hour'] = np.where(
        ((merged_other_df['Output Qty'] > 0) | (merged_other_df['MakeReady'] > 0)) & 
        merged_other_df['Working Hours'].isna(), 
        'yes', 
        'no'
    )
    merged_other_df['Employee Number'].fillna(merged_other_df['Member ID'], inplace=True)
    
    # Apply functions and calculate bonuses
    merged_other_df['Silver'] = merged_other_df.apply(lambda row: silver_eligibility(row) and not gold_eligibility(row), axis=1)
    merged_other_df['Gold'] = merged_other_df.apply(gold_eligibility, axis=1)
    merged_other_df['Silver Bonus'] = merged_other_df['Working Hours'] * merged_other_df['Silver Rate'] * merged_other_df['Silver']
    merged_other_df['Gold Bonus'] = merged_other_df['Working Hours'] * merged_other_df['Gold Rate'] * merged_other_df['Gold']
    
    # Replace NaN values
    merged_other_df['Silver Bonus'].fillna(0, inplace=True)
    merged_other_df['Gold Bonus'].fillna(0, inplace=True)
    
    return merged_other_df

# Calculate MakeReady Count
def make_ready_count(group):
    process = group['Process'].iloc[0]
    
    if process == "Die Cutting":
        return group['Die Number'].nunique()
    elif process == "Printing":
        product_code_count = group.groupby(['Product', 'Main product code'])['Makeup Style'].nunique().sum()
        return group['Product'].nunique() * group['Main product code'].nunique() * product_code_count
    else:
        return group.groupby(['Product', 'Main product code']).ngroups

# Calculate Performance: Gold
def flag_gold_sheeting(row):
    # working_hours = row['Working Hours'].total_seconds() / 3600  # Convert Timedelta to hours
    working_hours = row['Working Hours']
    paper_number = row['Paper Number (sheet)']
    
    if 7 < working_hours <= 8 and paper_number >= 80000:
        return True
    elif 8 < working_hours <= 10 and paper_number >= 100000:
        return True
    elif 10 < working_hours <= 12 and paper_number >= 120000:
        return True
    elif working_hours >= 12 and paper_number >= 120000 + math.floor(working_hours - 12) * 10000:
        return True
    else:
        return False
    
def calculate_gold_bonus(row):
    # working_hours = row['Working Hours'].total_seconds() / 3600  # Convert Timedelta to hours
    working_hours = row['Working Hours']
    gold_rate = row['Gold Rate'] 
    if row['Gold'] is True:
        return working_hours * gold_rate
    else:
        return 0

def check_conditions(wh, mr, oq, max_wh, thresholds):
    if wh <= max_wh:
        for make_ready, (min_wh, min_oq) in thresholds.items():
            if mr == make_ready and wh >= min_wh and oq >= min_oq:
                return True
    return False

def silver_eligibility(row):
    wh = row['Working Hours']
    mr = row['MakeReady']
    oq = row['Output Qty']
    re = row['Revenue']  
    nl = row['Number of Lines']
    conditions = [] 
    
    if row['Process'] == "Die Cutting":
        if 8 < wh <= 10:
            conditions = [
                (mr == 1 and wh >= 8 and oq >= 34000),
                (mr == 2 and wh >= 6 and oq >= 25800),
                (mr == 3 and wh >= 4 and oq >= 17200),
                (mr == 4 and wh >= 2 and oq >= 8600),
                (mr >= 5 and wh > 0 and oq >= 0)
            ]
        elif 10 < wh <= 12:
            conditions = [
                (mr == 1 and wh >= 10 and oq >= 43000),
                (mr == 2 and wh >= 8 and oq >= 34400),
                (mr == 3 and wh >= 6 and oq >= 25800),
                (mr == 4 and wh >= 4 and oq >= 17200),
                (mr >= 5 and wh > 0 and oq >= 0)
            ]
        elif wh >= 12:
            conditions = [
                (mr == 1 and wh >= 12 and oq >= 51600),
                (mr == 2 and wh >= 10 and oq >= 43000),
                (mr == 3 and wh >= 8 and oq >= 34400),
                (mr == 4 and wh >= 6 and oq >= 25800),
                (mr >= 5 and wh > 0 and oq >= 0)
            ]
    elif row['Process'] in ("Gluing", "WindowPatching"):
        if nl == 1:
            conditions = [
                (8 < wh <= 10 and re >= 28000),
                (10 < wh <= 12 and re >= 35000),
                (wh >= 12 and re >= 42000)
            ]
        else:
            conditions = [
                (8 < wh <= 10 and re >= 28000 * 0.75 * nl),
                (10 < wh <= 12 and re >= 35000 * 0.75 * nl),
                (wh >= 12 and re >= 42000 * 0.75 * nl)
            ]
    elif row['Process']=="Printing_CX102":
        thresholds_8h={
            1:(8,64000),
            2:(7,56000),
            3:(6,48000),
            4:(5,40000),
            5:(4,32000),
            6:(3,24000),
            7:(2,16000),
            8:(1,0),
            9:(0,0),
        }
        thresholds_10h={
            1:(10,80000),
            2:(9,72000),
            3:(8,64000),
            4:(7,56000),
            5:(6,48000),
            6:(5,40000),
            7:(4,32000),
            8:(3,24000),
            9:(2,16000),
            10:(1,0),
            11:(0,0),
        }
        thresholds_12h={
            1:(12,96000),
            2:(11,88000),
            3:(10,80000),
            4:(9,72000),
            5:(8,64000),
            6:(7,56000),
            7:(6,48000),
            8:(5,40000),
            9:(4,32000),
            10:(3,24000),
            11:(2,16000),
            12:(1,0),
            13:(0,0),
        }
        return(
            check_conditions(row['Working Hours'],row['MakeReady'],row['Output Qty'],8,thresholds_8h)or
            check_conditions(row['Working Hours'],row['MakeReady'],row['Output Qty'],10,thresholds_10h)or
            check_conditions(row['Working Hours'],row['MakeReady'],row['Output Qty'],12,thresholds_12h)
        )
    elif row['Process']=="Printing_CX104":
        thresholds_8h={
            1:(8,68000),
            2:(7,59500),
            3:(6,51000),
            4:(5,42500),
            5:(4,34000),
            6:(3,25500),
            7:(2,17000),
            8:(1,0),
            9:(0,0),
        }
        thresholds_10h={
            1:(10,85000),
            2:(9,76500),
            3:(8,68000),
            4:(7,59500),
            5:(6,51000),
            6:(5,42500),
            7:(4,34000),
            8:(3,25500),
            9:(2,17000),
            10:(1,0),
            11:(0,0),
        }
        thresholds_12h={
            1:(12,102000),
            2:(11,93500),
            3:(10,85000),
            4:(9,76500),
            5:(8,68000),
            6:(7,59500),
            7:(6,51000),
            8:(5,42500),
            9:(4,34000),
            10:(3,25500),
            11:(2,17000),
            12:(1,0),
            13:(0,0),
        }
        return(
            check_conditions(row['Working Hours'],row['MakeReady'],row['Output Qty'],8,thresholds_8h)or
            check_conditions(row['Working Hours'],row['MakeReady'],row['Output Qty'],10,thresholds_10h)or
            check_conditions(row['Working Hours'],row['MakeReady'],row['Output Qty'],12,thresholds_12h)
        )
    return any(conditions)
    # else:
    #     return False

def gold_eligibility(row):
    wh = row['Working Hours']
    mr = row['MakeReady']
    oq = row['Output Qty']
    re = row['Revenue']
    nl = row['Number of Lines']
    conditions = [] 
    
    if row['Process'] == "Die Cutting":
        if 8 < wh <= 10:
            conditions = [
                (mr == 1 and wh >= 8 and oq >= 42400),
                (mr == 2 and wh >= 6.5 and oq >= 34450),
                (mr == 3 and wh >= 5 and oq >= 26500),
                (mr == 4 and wh >= 3.5 and oq >= 18550),
                (mr >= 5 and wh > 0 and oq >= 0)
            ]
        elif 10 < wh <= 12:
            conditions = [
                (mr == 1 and wh >= 10 and oq >= 53000),
                (mr == 2 and wh >= 8.5 and oq >= 45050),
                (mr == 3 and wh >= 7 and oq >= 37100),
                (mr == 4 and wh >= 5.5 and oq >= 29150),
                (mr >= 5 and wh > 0 and oq >= 0)
            ]
        # elif 10 < wh <= 12:
        elif wh >= 12:
            conditions = [
                (mr == 1 and wh >= 12 and oq >= 63600),
                (mr == 2 and wh >= 10.5 and oq >= 55650),
                (mr == 3 and wh >= 9 and oq >= 47700),
                (mr == 4 and wh >= 7.5 and oq >= 39750),
                (mr >= 5 and wh > 0 and oq >= 0)
            ]
    elif row['Process'] in ("Gluing", "WindowPatching"):
        if nl == 1:
            conditions = [
                (8 < wh <= 10 and re >= 32000),
                (10 < wh <= 12 and re >= 40000),
                (wh >= 12 and re >= 48000)
            ]
        else:
            conditions = [
                (8 < wh <= 10 and re >= 32000 * 0.75 * nl),
                (10 < wh <= 12 and re >= 40000 * 0.75 * nl),
                (wh >= 12 and re >= 48000 * 0.75 * nl)
            ]
    elif row['Process']=="Printing_CX102":
        thresholds_8h={
            1:(8,72000),
            2:(7.15,64350),
            3:(6.3,56700),
            4:(5.45,49050),
            5:(4.6,41400),
            6:(3.75,33750),
            7:(2.9,26100),
            8:(2.05,18450),
            9:(1.2,0),
        }
        thresholds_10h={    
            1:(10,90000),
            2:(9.15,82350),
            3:(8.3,74700),
            4:(7.45,67050),
            5:(6.6,59400),
            6:(5.75,51750),
            7:(4.9,44100),
            8:(4.05,36450),
            9:(3.2,28800),
            10:(2.35,21150),
            11:(1.5,13500),
            12:(0.65,0),
        }
        thresholds_12h={
            1:(12,108000),
            2:(11.15,100350),
            3:(10.3,92700),
            4:(9.45,85050),
            5:(8.6,77400),
            6:(7.75,69750),
            7:(6.9,62100),
            8:(6.05,54450),
            9:(5.2,46800),
            10:(4.35,39150),
            11:(3.5,31500),
            12:(2.65,23850),
            13:(1.8,16200),
            14:(0.95,0),
        }
        return(
            check_conditions(row['Working Hours'],row['MakeReady'],row['Output Qty'],8,thresholds_8h)or
            check_conditions(row['Working Hours'],row['MakeReady'],row['Output Qty'],10,thresholds_10h)or
            check_conditions(row['Working Hours'],row['MakeReady'],row['Output Qty'],12,thresholds_12h)
        )
    elif row['Process']=="Printing_CX104":
        thresholds_8h={
            1:(8,76000),
            2:(7.15,67925),
            3:(6.3,59850),
            4:(5.45,51775),
            5:(4.6,43700),
            6:(3.75,35625),
            7:(2.9,27550),
            8:(2.05,19475),
            9:(1.2,0),
        }
        thresholds_10h={    
            1:(10,95000),
            2:(9.15,86925),
            3:(8.3,78850),
            4:(7.45,70775),
            5:(6.6,62700),
            6:(5.75,54625),
            7:(4.9,46550),
            8:(4.05,38475),
            9:(3.2,30400),
            10:(2.35,22325),
            11:(1.5,14250),
            12:(0.65,0),
        }
        thresholds_12h={
            1:(12,114000),
            2:(11.15,105925),
            3:(10.3,97850),
            4:(9.45,89775),
            5:(8.6,81700),
            6:(7.75,73625),
            7:(6.9,65550),
            8:(6.05,57475),
            9:(5.2,49400),
            10:(4.35,41325),
            11:(3.5,33250),
            12:(2.65,25175),
            13:(1.8,17100),
            14:(0.95,0),
        }
        return(
            check_conditions(row['Working Hours'],row['MakeReady'],row['Output Qty'],8,thresholds_8h)or
            check_conditions(row['Working Hours'],row['MakeReady'],row['Output Qty'],10,thresholds_10h)or
            check_conditions(row['Working Hours'],row['MakeReady'],row['Output Qty'],12,thresholds_12h)
        )
    return any(conditions)
    # else:
    #     return False

## Merge Reports
# Merge Reports

def adjust_merged_sheeting_df(merged_sheeting_df):
    merged_sheeting_df['Process'] = 'Sheeting'
    merged_sheeting_df['Output Qty'] = merged_sheeting_df['Paper Number (sheet)']
    merged_sheeting_df['MakeReady'] = 1
    merged_sheeting_df['Number of Lines'] = 1
    merged_sheeting_df['Revenue'] = 0
    merged_sheeting_df['Silver'] = False
    merged_sheeting_df['Silver Bonus'] = 0
    return merged_sheeting_df

def concatenate_dataframes(df1, df2, common_columns):
    return pd.concat([df1[common_columns], df2[common_columns]], ignore_index=True)

def generate_bonus_report(merged_df):
    return merged_df[(merged_df['Silver'] == True) | (merged_df['Gold'] == True)]

def generate_not_reported_working_hour_report(merged_df):
    not_reported_working_hour_report = merged_df[merged_df['flag_not_report_working_hour'] == 'yes']
    return not_reported_working_hour_report.groupby('Employee Number').agg({
        'Process': 'first',
        'MakeReady': 'sum',
        'Output Qty': 'sum',
        'Revenue': 'sum'
    }).reset_index()

##Plotting Functions
def create_bar_chart(data, x, y, hue, title, xlabel, ylabel, pdf):
    plt.figure(figsize=(12, 6))
    barplot = sns.barplot(x=x, y=y, hue=hue, data=data, palette='viridis')
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    
    # Add data labels
    for p in barplot.patches:
        barplot.annotate(format(p.get_height(), '.2f'),
                         (p.get_x() + p.get_width() / 2., p.get_height()),
                         ha='center', va='center',
                         xytext=(0, 9),
                         textcoords='offset points')
    
    plt.tight_layout()
    pdf.savefig()  # saves the current figure into a pdf page
    plt.close()

def create_horizontal_bar_chart(data, x, y, hue, title, xlabel, ylabel, pdf):
    plt.figure(figsize=(12, 6))
    barplot = sns.barplot(x=x, y=y, hue=hue, data=data, palette='viridis')
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    
    # Add data labels
    for p in barplot.patches:
        barplot.annotate(format(p.get_width(), '.2f'),
                         (p.get_width(), p.get_y() + p.get_height() / 2.),
                         ha='center', va='center',
                         xytext=(9, 0),
                         textcoords='offset points')
    
    plt.tight_layout()
    pdf.savefig()  # saves the current figure into a pdf page
    plt.close()

## Save to Excel
def save_reports_to_excel(merged_df, bonus_report, not_reported_working_hour_report, input_directory):
    """
    Save the provided DataFrames to an Excel file with two sheets.
    
    Parameters:
        merged_df (pd.DataFrame): The DataFrame used to determine date range for filename.
        bonus_report (pd.DataFrame): DataFrame to be saved in the 'Bonus Report' sheet.
        not_reported_working_hour_report (pd.DataFrame): DataFrame to be saved in the 'Not Reported Working Hour' sheet.
        
    Returns:
        str: The filename where the DataFrames were saved.
    """
    # Find the minimum and maximum Start Date
    min_date = pd.to_datetime(merged_df['Start Date']).min().strftime('%Y-%m-%d')
    max_date = pd.to_datetime(merged_df['Start Date']).max().strftime('%Y-%m-%d')
    
    # Create the filename
    filename = f"{input_directory}/Production Report from {min_date} to {max_date}.xlsx"
    
    # Save the reports to Excel file with two tabs
    with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
        bonus_report.to_excel(writer, sheet_name='Bonus Report', index=False)
        not_reported_working_hour_report.to_excel(writer, sheet_name='Not Reported Working Hour', index=False)
    
    return filename




