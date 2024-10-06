# Salary Calculation functions

def calculate_employee_salary(row, holidays_df, start_date, end_date):
    print(f"\nCalculating salary for Employee {row['Employee Number']}:")
    print(f"  Department: {row['Department']}")
    print(f"  Total Hours: {row['Total Hours']}")
    print(f"  Working Days: {row['Working Days']}")
    
    # For Temp employees or employees without payrate data, just return total hours
    if pd.isna(row['REG Pay Rate (正常时薪)']) or row['Department'] == 'Temp':
        return pd.Series({
            'Salary': 0,
            'Regular Pay': 0,
            'Overtime Pay': 0,
            'Total Compensation': 0
        })
    
    print(f"  不需要计算: {row['不需要计算']}")
    print(f"  Follow 打卡时间: {row['Follow 打卡时间']}")
    print(f"  Annual Or Hourly: {row['Annual Or Hourly']}")
    print(f"  REG Pay Rate: {row['REG Pay Rate (正常时薪)']}")
    print(f"  OT Pay Rate: {row['OT Pay Rate (加班时薪）']}")
    
    # Check for missing crucial information
    if pd.isna(row['Annual Or Hourly']) or not any(keyword in str(row['Annual Or Hourly']).lower() for keyword in ['annual', 'hourly', 'daily']):
        print("  Missing or invalid Annual Or Hourly value. Setting salary to 0.")
        return pd.Series({'Salary': 0, 'Regular Pay': 0, 'Overtime Pay': 0, 'Total Compensation': 0})
    
    # Handle NaN values
    row['不需要计算'] = 'No' if pd.isna(row['不需要计算']) else row['不需要计算']
    row['Follow 打卡时间'] = 'No' if pd.isna(row['Follow 打卡时间']) else row['Follow 打卡时间']
    row['OT Pay Rate (加班时薪）'] = row['REG Pay Rate (正常时薪)'] if pd.isna(row['OT Pay Rate (加班时薪）']) else row['OT Pay Rate (加班时薪）']
    row['Bi-weekly 加班费触发小时（有holiday）'] = 80 if pd.isna(row['Bi-weekly 加班费触发小时（有holiday）']) else row['Bi-weekly 加班费触发小时（有holiday）']
    row['Bi-weekly 加班费触发小时（没有holiday）'] = 80 if pd.isna(row['Bi-weekly 加班费触发小时（没有holiday）']) else row['Bi-weekly 加班费触发小时（没有holiday）']

    print(f"  Adjusted values:")
    print(f"    不需要计算: {row['不需要计算']}")
    print(f"    Follow 打卡时间: {row['Follow 打卡时间']}")
    print(f"    OT Pay Rate: {row['OT Pay Rate (加班时薪）']}")
    print(f"    Bi-weekly 加班费触发小时（有holiday）: {row['Bi-weekly 加班费触发小时（有holiday）']}")
    print(f"    Bi-weekly 加班费触发小时（没有holiday）: {row['Bi-weekly 加班费触发小时（没有holiday）']}")

    if row['不需要计算'] == 'Yes':
        print("  不需要计算 = Yes, Salary = 0")
        return pd.Series({'Salary': 0, 'Regular Pay': 0, 'Overtime Pay': 0, 'Total Compensation': 0})
    
    annual_or_hourly = str(row['Annual Or Hourly']).strip().lower()

    if 'daily' in annual_or_hourly:
        salary = row['Working Days'] * row['REG Pay Rate (正常时薪)']
        print(f"  Daily, Salary = {row['Working Days']} * {row['REG Pay Rate (正常时薪)']} = {salary}")
        return pd.Series({'Salary': salary, 'Regular Pay': salary, 'Overtime Pay': 0, 'Total Compensation': salary})
    
    elif 'annual' in annual_or_hourly:
        salary = row['REG Pay Rate (正常时薪)']
        print(f"  Annual, Salary = {row['REG Pay Rate (正常时薪)']} = {salary}")
        return pd.Series({'Salary': salary, 'Regular Pay': salary, 'Overtime Pay': 0, 'Total Compensation': salary})
    
    elif 'hourly' in annual_or_hourly:
        holiday_in_period = any(h in holidays_df['Date'].values for h in pd.date_range(start_date, end_date))
        
        if row['Follow 打卡时间'] == 'Yes':
            salary = row['Total Hours'] * row['REG Pay Rate (正常时薪)']
            print(f"  Hourly, Follow 打卡时间 = Yes, Salary = {row['Total Hours']} * {row['REG Pay Rate (正常时薪)']} = {salary}")
            return pd.Series({'Salary': salary, 'Regular Pay': salary, 'Overtime Pay': 0, 'Total Compensation': salary})
        else:
            if holiday_in_period:
                regular_hours = row['Bi-weekly 加班费触发小时（有holiday）']
                print(f"  Holiday in period, using 加班费触发小时（有holiday）: {regular_hours}")
            else:
                regular_hours = row['Bi-weekly 加班费触发小时（没有holiday）']
                print(f"  No holiday in period, using 加班费触发小时（没有holiday）: {regular_hours}")
            
            overtime_hours = max(0, row['Total Hours'] - regular_hours)
            regular_pay = regular_hours * row['REG Pay Rate (正常时薪)']
            overtime_pay = overtime_hours * row['OT Pay Rate (加班时薪）']
            total_salary = regular_pay + overtime_pay
            print(f"  Hourly, Follow 打卡时间 = No, Salary = ({regular_hours} * {row['REG Pay Rate (正常时薪)']} + {overtime_hours} * {row['OT Pay Rate (加班时薪）']}) = {total_salary}")
            return pd.Series({'Salary': total_salary, 'Regular Pay': regular_pay, 'Overtime Pay': overtime_pay, 'Total Compensation': total_salary})
    
    else:
        print(f"  Unknown Annual Or Hourly value: {row['Annual Or Hourly']}, Setting salary to 0")
        return pd.Series({'Salary': 0, 'Regular Pay': 0, 'Overtime Pay': 0, 'Total Compensation': 0})

def calculate_salary(timesheet_df, payrate_df, holidays_df, production_df, start_date, previous_biweekly_hours):
    print("\nCalculating Salary")
    
    # Convert start_date to datetime
    start_date = pd.to_datetime(start_date)
    end_date = start_date + timedelta(days=13)  # Biweekly period
    print(f"Calculation period: {start_date.date()} to {end_date.date()}")
    
    # Filter timesheet for the biweekly period
    timesheet_df = timesheet_df[(timesheet_df['Start Date'] >= start_date) & (timesheet_df['Start Date'] <= end_date)]
    
    # Calculate total working hours and days for each employee
    employee_totals = timesheet_df.groupby('Employee Number').agg({
        'Working Hours': 'sum',
        'Start Date': 'nunique'
    }).reset_index()
    employee_totals.columns = ['Employee Number', 'Total Hours', 'Working Days']
    print("\nEmployee Totals (sample):")
    print(employee_totals.head())
    
    # Merge with payrate data
    if 'Employee ID' in payrate_df.columns:
        merged_df = pd.merge(employee_totals, payrate_df, left_on='Employee Number', right_on='Employee ID', how='left')
    else:
        print("Warning: 'Employee ID' column not found in payrate data. Merging on 'Employee Number'.")
        merged_df = pd.merge(employee_totals, payrate_df, on='Employee Number', how='left')
    
    # Check for unmatched employees
    unmatched = merged_df[merged_df['REG Pay Rate (正常时薪)'].isna()]
    if not unmatched.empty:
        print(f"\nWarning: {len(unmatched)} employees not matched with payrate data:")
        print(unmatched[['Employee Number', 'Total Hours', 'Working Days']])
    
    merged_df['Salary'] = merged_df.apply(lambda row: calculate_employee_salary(row, holidays_df, start_date, end_date), axis=1)
    
    # Calculate holiday pay
    def calculate_holiday_pay(employee_id, holiday_date, merged_df, timesheet_df, previous_biweekly_hours):
        employee_data = merged_df[merged_df['Employee Number'] == employee_id].iloc[0]
        employee_timesheet = timesheet_df[(timesheet_df['Employee Number'] == employee_id) & 
                                          (timesheet_df['Start Date'].dt.date == holiday_date.date())]
        
        # Part 1: Pay for adjusted work hours on the holiday
        if not employee_timesheet.empty:
            holiday_hours = employee_timesheet['Working Hours'].sum()
            part1_pay = holiday_hours * employee_data['OT Pay Rate (加班时薪）']
        else:
            part1_pay = 0
        
        # Part 2: Additional holiday pay based on previous 2 biweekly periods
        current_period_hours = employee_data['Total Hours']
        total_4_weeks_hours = sum(previous_biweekly_hours.get(employee_id, [0, 0])) + current_period_hours
        
        # Calculate the cap based on trigger hours
        cap_hours = 0
        for i in range(2):  # Check for holidays in current and previous biweekly period
            period_start = start_date - timedelta(days=14*i)
            period_end = period_start + timedelta(days=13)
            if any(h in holidays_df['Date'].values for h in pd.date_range(period_start, period_end)):
                cap_hours += employee_data['Bi-weekly 加班费触发小时（有holiday）']
            else:
                cap_hours += employee_data['Bi-weekly 加班费触发小时（没有holiday）']
        
        capped_hours = min(total_4_weeks_hours, cap_hours)
        part2_pay = (capped_hours / 10) * employee_data['REG Pay Rate (正常时薪)']
        
        total_holiday_pay = part1_pay + part2_pay
        print(f"  Holiday Pay for {employee_id} on {holiday_date.date()}: Part1 = {part1_pay}, Part2 = {part2_pay}, Total = {total_holiday_pay}")
        return total_holiday_pay
    
    # Calculate holiday pay
    for _, holiday in holidays_df.iterrows():
        if start_date <= holiday['Date'] <= end_date:
            print(f"\nCalculating Holiday Pay for {holiday['Date'].date()}:")
            merged_df[f'Holiday Pay {holiday["Date"].strftime("%m-%d")}'] = merged_df['Employee Number'].apply(
                lambda x: calculate_holiday_pay(x, holiday['Date'], merged_df, timesheet_df, previous_biweekly_hours)
            )
    
    # Add bonus from production report
    production_df = production_df[(production_df['Date'] >= start_date) & (production_df['Date'] <= end_date)]
    bonus_totals = production_df.groupby('Employee ID')['Bonus'].sum().reset_index()
    merged_df = pd.merge(merged_df, bonus_totals, left_on='Employee Number', right_on='Employee ID', how='left')
    merged_df['Bonus'] = merged_df['Bonus'].fillna(0)
    
    # Calculate total compensation
    merged_df['Total Compensation'] = merged_df.apply(
        lambda row: row['Salary'] + row['Bonus'] if row['Department'] != 'Temp' else 0,
        axis=1
    )
    
    # Prepare data for next period
    next_period_hours = merged_df.set_index('Employee Number')['Total Hours'].to_dict()
    
    return merged_df, next_period_hours

def calculate_salary(timesheet_df, payrate_df, holidays_df, production_df, start_date, previous_biweekly_hours):
    print("\nCalculating Salary")
    
    # Convert start_date to datetime
    start_date = pd.to_datetime(start_date)
    end_date = start_date + pd.Timedelta(days=13)  # Biweekly period
    print(f"Calculation period: {start_date.date()} to {end_date.date()}")
    
    # Filter timesheet for the biweekly period
    timesheet_df = timesheet_df[(timesheet_df['Start Date'] >= start_date) & (timesheet_df['Start Date'] <= end_date)]
    
    # Calculate total working hours and days for each employee
    employee_totals = timesheet_df.groupby('Employee Number').agg({
        'Working Hours': 'sum',
        'Start Date': 'nunique',
        'Department': 'first',
        'First name': 'first',
        'Last name': 'first'
    }).reset_index()
    employee_totals.columns = ['Employee Number', 'Total Hours', 'Working Days', 'Department', 'First name', 'Last name']
    
    # Merge with payrate data
    # merged_df = pd.merge(employee_totals, payrate_df, on='Employee Number', how='left')

    # Print column names for debugging
    print("Columns in employee_totals:")
    print(employee_totals.columns)
    print("\nColumns in payrate_df:")
    print(payrate_df.columns)
    
    # Determine the matching column
    if 'Employee Number' in payrate_df.columns:
        match_column = 'Employee Number'
    elif 'Employee ID' in payrate_df.columns:
        match_column = 'Employee ID'
    else:
        print("Error: No suitable matching column found in payrate_df")
        return pd.DataFrame(), {}
    
    # Merge with payrate data, but keep all employees even if they don't have a match
    merged_df = pd.merge(employee_totals, payrate_df, left_on='Employee Number', right_on=match_column, how='left')
    
    
    # Check for unmatched employees
    unmatched = merged_df[merged_df['REG Pay Rate (正常时薪)'].isna()]
    if not unmatched.empty:
        print(f"\nWarning: {len(unmatched)} employees not matched with payrate data:")
        print(unmatched[['Employee Number', 'Total Hours', 'Working Days']])
    
    # Calculate basic salary
    # merged_df['Salary'] = merged_df.apply(lambda row: calculate_employee_salary(row, holidays_df, start_date, end_date), axis=1)
    salary_info = merged_df.apply(lambda row: calculate_employee_salary(row, holidays_df, start_date, end_date), axis=1)
    merged_df = pd.concat([merged_df, salary_info], axis=1)
    
    # Calculate holiday pay (excluding Temp employees)
    for _, holiday in holidays_df.iterrows():
        if start_date <= holiday['Date'] <= end_date:
            print(f"\nCalculating Holiday Pay for {holiday['Date'].date()}:")
            merged_df[f'Holiday Pay {holiday["Date"].strftime("%m-%d")}'] = merged_df.apply(
                lambda row: calculate_holiday_pay(row, holiday['Date'], merged_df, timesheet_df, previous_biweekly_hours) if row['Department'] != 'Temp' else 0,
                axis=1
            )
            
    # Handle production bonus
    if production_df is not None and 'Date' in production_df.columns:
        production_df = production_df[(production_df['Date'] >= start_date) & (production_df['Date'] <= end_date)]
        bonus_totals = production_df.groupby('Employee ID')['Bonus'].sum().reset_index()
        merged_df = pd.merge(merged_df, bonus_totals, left_on='Employee Number', right_on='Employee ID', how='left')
        merged_df['Bonus'] = merged_df['Bonus'].fillna(0)
    else:
        merged_df['Bonus'] = 0
    
    # Adjust Total Compensation to include Bonus for all employees
    merged_df['Total Compensation'] = merged_df['Total Compensation'] + merged_df['Bonus']
    
    print("\nFinal Calculations (sample):")
    print(merged_df[['Employee Number', 'Department', 'Total Hours', 'Salary', 'Bonus', 'Total Compensation']].head())
    
    next_period_hours = merged_df.set_index('Employee Number')['Total Hours'].to_dict()
    
    return merged_df, next_period_hours

# Processor 
def process_data(timesheet_df, schedule_df, holidays_df, production_df, payrate_df, start_date, num_periods=1):
    changes = []
    all_salary_dfs = []
    previous_4_weeks_hours = {}

    if timesheet_df is not None and not timesheet_df.empty:
        print(f"Timesheet data shape: {timesheet_df.shape}")
        timesheet_df, vacation_df = process_vacations(timesheet_df)
        timesheet_df = combine_time(timesheet_df)
        timesheet_df, business_changes = adjust_business_hours(timesheet_df)
        changes.extend(business_changes)
        
        if schedule_df is not None and not schedule_df.empty:
            timesheet_df, schedule_changes, schedule_alerts = update_from_schedule(timesheet_df, schedule_df)
            changes.extend(schedule_changes)
        
        timesheet_df, lunch_changes = adjust_lunch_time(timesheet_df)
        changes.extend(lunch_changes)
    else:
        print("No timesheet data available.")
        return None, None, None, None

    changes_df = pd.DataFrame(changes)
    start_date = pd.to_datetime(start_date)

    for period in range(num_periods):
        period_start = start_date + timedelta(days=14 * period)
        period_end = period_start + timedelta(days=13)

        print(f"\nProcessing period {period + 1}: {period_start.date()} to {period_end.date()}")

        period_timesheet = timesheet_df[(timesheet_df['Start Date'] >= period_start) & (timesheet_df['Start Date'] <= period_end)]
        
        try:
            salary_df, next_period_hours = calculate_salary(period_timesheet, payrate_df, holidays_df, production_df, period_start, previous_4_weeks_hours)
            salary_df['Period Start'] = period_start
            salary_df['Period End'] = period_end
            all_salary_dfs.append(salary_df)

            for emp, hours in next_period_hours.items():
                if emp in previous_4_weeks_hours:
                    previous_4_weeks_hours[emp] = previous_4_weeks_hours[emp][1:] + [hours]
                else:
                    previous_4_weeks_hours[emp] = [0, 0, 0, hours]

            print(f"Processed data for {len(salary_df)} employees")
        except Exception as e:
            print(f"Error processing period {period + 1}: {str(e)}")
            print("Traceback:")
            import traceback
            traceback.print_exc()

    if all_salary_dfs:
        combined_salary_df = pd.concat(all_salary_dfs, ignore_index=True)
        print(f"Combined data shape: {combined_salary_df.shape}")
    else:
        print("No data was processed. Creating an empty DataFrame.")
        combined_salary_df = pd.DataFrame()

    return timesheet_df, vacation_df, changes_df, schedule_alerts, combined_salary_df