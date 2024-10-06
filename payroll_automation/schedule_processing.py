# Combine timesheet and schedules functions

def get_department(file_path):
    return os.path.basename(file_path).split()[0]

def process_timesheet(file_path):
    df = read_excel_safe(file_path, [
        "Start Date", "Start time", "End Date", "End time", 
        "Employee Number", "First name", "Last name", "Job", "Employee notes"
    ])
    if not df.empty:
        # Forward fill Employee Number, First name, and Last name
        df['Employee Number'] = df['Employee Number'].ffill()
        df['First name'] = df['First name'].ffill()
        df['Last name'] = df['Last name'].ffill()
        
        # Drop rows where date and time fields are all empty
        df = df.dropna(subset=['Start Date', 'Start time', 'End Date', 'End time'], how='all')
        
        # Add Department column
        df['Department'] = get_department(file_path)

        df = df.sort_values(by=['Employee Number', 'First name', 'Last name', 'Start time'])

    return df

def process_temp_timesheet(file_path):
    df = read_excel_safe(file_path, ["Start Date", "Start time", "End Date", "End time", "First name", "Last name", "Team", "Job", "Employee notes"])
    if not df.empty:
        # Rename 'Team' to 'Employee Number'
        df = df.rename(columns={'Team': 'Employee Number'})
        df['Employee Number'] = df['Employee Number'].ffill()
        df['First name'] = df['First name'].ffill()
        df['Last name'] = df['Last name'].ffill()
        
        # Drop rows where date and time fields are all empty
        df = df.dropna(subset=['Start Date', 'Start time', 'End Date', 'End time'], how='all')
        
        # Add Department column
        df['Department'] = get_department(file_path)

        df = df.sort_values(by=['Employee Number', 'First name', 'Last name', 'Start time'])
    return df

def process_schedule(file_path):
    df = read_excel_safe(file_path, ["Date", "Start", "End", "Users", "Availability status"])
    if not df.empty:
        # Drop rows where Start is "All Day" or End is empty
        df = df[(df['Start'] != "All Day") & (df['Availability status'] != "Unavailable") & (df['End'].notna())]
        
        # Add Department column
        df['Department'] = get_department(file_path)
    return df