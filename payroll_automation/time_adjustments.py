# Time adjustment functions

def process_vacations(df):
    print("\nStep 1: Processing Vacations")
    
    # Make a copy to avoid SettingWithCopyWarning
    df = df.copy()
    
    # Sort the dataframe by Employee Number and Start Date
    df = df.sort_values(['Employee Number', 'Start Date'], ascending=[True, True])
    
    # Create a new column to identify consecutive vacation days
    df['is_vacation'] = df['Job'] == 'Vacation - paid'
    df['vacation_group'] = (
        (df['is_vacation'] != df['is_vacation'].shift()) | 
        (df['Employee Number'] != df['Employee Number'].shift())
    ).cumsum()
    
    # Group by employee and vacation group
    vacation_groups = df[df['is_vacation']].groupby(['Employee Number', 'vacation_group'])
    vacation_counts = vacation_groups.size()
    
    # Create a DataFrame to store vacation information
    vacation_info = []
    
    # Process all vacation periods
    print("\nAll vacation periods:")
    for (employee, group), count in vacation_counts.items():
        vacation_data = vacation_groups.get_group((employee, group)).iloc[0]
        print(f"Employee {vacation_data['Employee Number']} ({vacation_data['First name']} {vacation_data['Last name']}) - Department: {vacation_data['Department']}: {count} days")
        vacation_info.append({
            'Employee Number': vacation_data['Employee Number'],
            'First Name': vacation_data['First name'],
            'Last Name': vacation_data['Last name'],
            'Department': vacation_data['Department'],
            'Vacation Days': count
        })
    
    # Create a DataFrame with vacation information
    vacation_df = pd.DataFrame(vacation_info)
    
    # Identify vacation records that are part of vacations longer than 1 day
    long_vacation_mask = df['is_vacation'] & (df.groupby(['Employee Number', 'vacation_group'])['is_vacation'].transform('count') > 1)
    
    # Print details of vacation records to be dropped
    dropped_vacations = df[long_vacation_mask]
    if not dropped_vacations.empty:
    
        # Drop vacation records that are part of vacations longer than 1 day
        original_count = len(df)
        df = df[~long_vacation_mask]
        dropped_count = original_count - len(df)
        print(f"Dropped {dropped_count} 'Vacation - paid' records that were part of vacations longer than 1 day")
    else:
        print("\nNo vacation records to be dropped.")
    
    # Drop the temporary columns
    df = df.drop(columns=['is_vacation', 'vacation_group'])
    
    return df, vacation_df

def adjust_start_time(dt):
    if dt.minute >= 0 and dt.minute <= 5:
        return dt.replace(minute=0)
    elif dt.minute >= 6 and dt.minute <= 35:
        return dt.replace(minute=30)
    else:
        return (dt + pd.Timedelta(hours=1)).replace(minute=0)

def adjust_end_time(dt):
    if dt.minute >= 0 and dt.minute <= 24:
        return dt.replace(minute=0)
    elif dt.minute >= 25 and dt.minute <= 54:
        return dt.replace(minute=30)
    else:
        return (dt + pd.Timedelta(hours=1)).replace(minute=0)

def combine_time(df):
    print("\nStep 2: Adjusting and Combining Time Records")
    
    # Make a copy to avoid SettingWithCopyWarning
    df = df.copy()
    
    original_count = len(df)
    
    # Convert date columns to datetime
    df['Start Date'] = pd.to_datetime(df['Start Date'], format='mixed', dayfirst=True)
    df['End Date'] = pd.to_datetime(df['End Date'], format='mixed', dayfirst=True)
    
    # Combine start date and start time into start datetime
    df['Start Datetime'] = pd.to_datetime(df['Start Date'].dt.strftime('%Y-%m-%d') + ' ' + df['Start time'], format='%Y-%m-%d %H:%M', errors='coerce')

    # Combine end date and end time into end datetime
    df['End Datetime'] = pd.to_datetime(df['End Date'].dt.strftime('%Y-%m-%d') + ' ' + df['End time'], format='%Y-%m-%d %H:%M', errors='coerce')
    
    # Drop rows where datetime conversion failed
    df.dropna(subset=['Start Datetime', 'End Datetime'], inplace=True)
    
    # Adjust start and end times
    df['Adjusted Start Datetime'] = df['Start Datetime'].apply(adjust_start_time)
    df['Adjusted End Datetime'] = df['End Datetime'].apply(adjust_end_time)
    
    # Calculate working hours
    df['Working Hours'] = (df['Adjusted End Datetime'] - df['Adjusted Start Datetime']).dt.total_seconds() / 3600

    # Sort the dataframe by 'Employee Number', 'First name', 'Last name', and 'Start Datetime'
    df = df.sort_values(by=['Employee Number', 'First name', 'Last name', 'Start Datetime'], ascending=[True, True, True, True]).reset_index(drop=True)

    # Identify rows where the end time is after midnight and the next record for the same employee starts at 00:00
    end_after_midnight = (df['Adjusted End Datetime'].dt.date > df['Adjusted Start Datetime'].dt.date)
    start_at_midnight = (df['Adjusted Start Datetime'].dt.hour == 0) & (df['Adjusted Start Datetime'].dt.minute == 0)
    same_employee = (df['Employee Number'] == df['Employee Number'].shift(-1)) & \
                    (df['First name'] == df['First name'].shift(-1)) & \
                    (df['Last name'] == df['Last name'].shift(-1))
    combine_rows = end_after_midnight & start_at_midnight.shift(-1) & same_employee

    # Print sample of records before combination
    print("\nSample of records before combination:")
    sample_before = df[combine_rows | combine_rows.shift(1, fill_value=False)].head(6)
    print(sample_before[['Employee Number', 'First name', 'Last name', 'Adjusted Start Datetime', 'Adjusted End Datetime', 'Working Hours']])

    # Combine the records
    for idx in df[combine_rows].index:
        df.loc[idx, 'Adjusted End Datetime'] = df.loc[idx+1, 'Adjusted End Datetime']
        df.loc[idx, 'Working Hours'] += df.loc[idx+1, 'Working Hours']
        df.loc[idx, 'End Date'] = df.loc[idx+1, 'End Date']
        df.loc[idx, 'End time'] = df.loc[idx+1, 'End time']
        df.loc[idx, 'End Datetime'] = df.loc[idx+1, 'End Datetime']
    
    # Remove the second part of combined pairs
    df = df[~(combine_rows.shift(1, fill_value=False) & same_employee)].reset_index(drop=True)

    combined_count = original_count - len(df)
    print(f"\nCombined {combined_count} records")
    print("\nSample of records after combination:")
    print(df[['Employee Number', 'First name', 'Last name', 'Adjusted Start Datetime', 'Adjusted End Datetime', 'Working Hours']].head())

    return df

def adjust_business_hours(df):
    print("\nStep 3: Adjusting Business Hours")
    
    # Make a copy to avoid SettingWithCopyWarning
    df = df.copy()
    
    changes = []
    
    # Identify Business department employees, excluding specific employee numbers
    business_mask = (df['Department'] == 'Business') & (~df['Employee Number'].isin(['EE109', 'EE037', 'EE034','EE059']))
    
    # Update start and end times for Business department
    for idx in df[business_mask].index:
        original_start = df.loc[idx, 'Adjusted Start Datetime']
        original_end = df.loc[idx, 'Adjusted End Datetime']
        new_start = original_start.replace(hour=9, minute=0)
        new_end = original_start.replace(hour=19, minute=30)
        
        if original_start != new_start or original_end != new_end:
            changes.append({
                'Employee Number': df.loc[idx, 'Employee Number'],
                'Full Name': f"{df.loc[idx, 'First name']} {df.loc[idx, 'Last name']}",
                'Original Start': original_start,
                'New Start': new_start,
                'Original End': original_end,
                'New End': new_end,
                'Reason': 'Adjusted business hours'
            })
            df.loc[idx, 'Adjusted Start Datetime'] = new_start
            df.loc[idx, 'Adjusted End Datetime'] = new_end
    
    # Recalculate working hours
    df.loc[business_mask, 'Working Hours'] = (df.loc[business_mask, 'Adjusted End Datetime'] - df.loc[business_mask, 'Adjusted Start Datetime']).dt.total_seconds() / 3600
    
    # Count affected records
    affected_records = len(changes)
    print(f"Adjusted {affected_records} Business department records")
    
    # Show sample of changes
    if affected_records > 0:
        print("Sample of changes:")
        print(pd.DataFrame(changes).head())
    
    return df, changes

def update_from_schedule(timesheet_df, schedule_df):
    print("\nStep 4: Updating Timesheet from Schedule")
    
    # Make copies to avoid SettingWithCopyWarning
    timesheet_df = timesheet_df.copy()
    schedule_df = schedule_df.copy()
    
    # Convert schedule date and time columns to datetime
    schedule_df['Date'] = pd.to_datetime(schedule_df['Date'], format='mixed', dayfirst=False)
    schedule_df['Start'] = pd.to_datetime(schedule_df['Date'].astype(str) + ' ' + schedule_df['Start'], format='mixed', errors='coerce')
    
    # For Temp employees, split the Users column into First name and Last name
    schedule_df[['First name', 'Last name']] = schedule_df['Users'].str.split(n=1, expand=True)
    
    # Create a full name column in both dataframes
    timesheet_df['Full Name'] = timesheet_df['First name'] + ' ' + timesheet_df['Last name']
    schedule_df['Full Name'] = schedule_df['First name'] + ' ' + schedule_df['Last name']
    
    # Convert Start Date to date for merging
    timesheet_df['Merge Date'] = timesheet_df['Start Date'].dt.date
    schedule_df['Merge Date'] = schedule_df['Date'].dt.date
    
    # Merge timesheet with schedule
    merged_df = pd.merge(
        timesheet_df,
        schedule_df[['Merge Date', 'Start', 'Full Name']],
        left_on=['Merge Date', 'Full Name'],
        right_on=['Merge Date', 'Full Name'],
        how='left'
    )
    
    changes = []
    alerts = []
    
    # Update start time if schedule start time is later, but not more than 1 hour earlier
    for idx, row in merged_df.iterrows():
        if pd.notna(row['Start']):
            time_diff = (row['Start'] - row['Start Datetime']).total_seconds() / 3600
            if -1 <= time_diff <= 1:
                original_start = row['Start Datetime']
                new_start = row['Start']
                merged_df.at[idx, 'Adjusted Start Datetime'] = new_start
                changes.append({
                    'Employee Number': row['Employee Number'],
                    'Full Name': row['Full Name'],
                    'Original Start': original_start,
                    'New Start': new_start,
                    'Time Difference (hours)': time_diff,
                    'Reason': 'Schedule start time adjustment'
                })
            elif abs(time_diff) > 1:
                alerts.append({
                    'Employee Number': row['Employee Number'],
                    'Full Name': row['Full Name'],
                    'Timesheet Start': row['Start Datetime'],
                    'Schedule Start': row['Start'],
                    'Time Difference (hours)': time_diff,
                    'Reason': 'Large time difference between timesheet and schedule'
                })
    
    # Recalculate working hours
    merged_df['Working Hours'] = (merged_df['Adjusted End Datetime'] - merged_df['Adjusted Start Datetime']).dt.total_seconds() / 3600
    
    # Drop unnecessary columns
    merged_df = merged_df.drop(columns=['Merge Date', 'Start', 'Full Name'])
    
    # Count affected records
    start_affected = len(changes)
    print(f"Updated {start_affected} start times from schedule")
    print(f"Found {len(alerts)} records with large time differences")
    
    # Show sample of changes
    if changes:
        print("Sample of changes:")
        changes_df = pd.DataFrame(changes)
        print(changes_df.head())
    
    # Show alerts
    if alerts:
        print("\nAlerts for large time differences:")
        alerts_df = pd.DataFrame(alerts)
        print(alerts_df)
    
    return merged_df, changes, alerts

def adjust_lunch_time(df):
    print("\nStep 5: Adjusting for Lunch Time")
    
    # Make a copy to avoid SettingWithCopyWarning
    df = df.copy()
    
    changes = []
    
    # Identify records with more than 7 working hours
    long_day_mask = df['Working Hours'] > 7
    
    for idx in df[long_day_mask].index:
        original_hours = df.loc[idx, 'Working Hours']
        new_hours = original_hours - 0.5
        
        changes.append({
            'Employee Number': df.loc[idx, 'Employee Number'],
            'Full Name': f"{df.loc[idx, 'First name']} {df.loc[idx, 'Last name']}",
            'Original Hours': original_hours,
            'New Hours': new_hours,
            'Reason': 'Subtracted 0.5 hours for lunch'
        })
        
        df.loc[idx, 'Working Hours'] = new_hours
    
    # Count affected records
    affected_records = len(changes)
    print(f"Adjusted {affected_records} records for lunch time")
    
    # Show sample of changes
    if affected_records > 0:
        print("Sample of changes:")
        print(pd.DataFrame(changes).head())
    
    return df, changes