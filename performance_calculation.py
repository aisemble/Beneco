# Load all udf functions

from util import *

print("\nPerformance Calculation Program Starting...")

# 1. Load Data
# Please change below 
# input_directory = " " # Can Manually change the folder path
input_directory = os.getcwd()  # This will set input_directory to the current working directory

print("\nIdentified file path:")
paths = find_files(input_directory)
print(paths)

print("\n1. Starting loading data from excel files...")
## 1.1 Sheeting
sheeting_df = load_and_process_data(paths["Sheeting_Operator_Report_Path"], process_sheeting_data)
print("\n1.1 Sheeting data loaded and processed.")

## 1.2 Time Sheet
Time_Sheet_df = load_and_process_data(paths["Time_Sheet_Path"], process_time_sheet_data)
print("\n1.2 Time sheet data loaded and processed.")

## 1.3 Die Code and Price Table
Die_Price_df = load_and_process_data(paths["Die_Price_df_Path"], process_die_price_data)
print("\n1.3 Die price data loaded and processed.")

## 1.4 Other Operator Report
other_df = load_and_process_data(paths["Other_Operator_Report_Path"], process_other_process_data)
print("\n1.4 Other operator report data loaded and processed.")

## 1.5 Operator Bonus Rate
Operator_Bonus_Rate_df = load_and_process_data(paths["Operator_Bonus_Rate_Path"], process_bonus_rate_data, skiprows=2)
print("\n1.5 Operator bonus rate data loaded and processed.")

# 2. Calculation
print("\n2. Starting calculations...")
## 2.1 Calculation for Sheeting
merged_sheeting_df = process_and_merge_data(sheeting_df, Time_Sheet_df, Operator_Bonus_Rate_df, clean_and_rename_columns, flag_gold_sheeting, calculate_gold_bonus)
print("\n2.1 Sheeting data merged and calculations completed.")

## 2.2. Calculation for other process
merged_other_df = process_and_calculate_revenue(other_df, Die_Price_df, Time_Sheet_df, Operator_Bonus_Rate_df,make_ready_count, silver_eligibility, gold_eligibility)
print("\n2.2 Other process data merged and calculations completed.")

## 2.3 Merge Reports
# Adjusting merged_sheeting_df
merged_sheeting_df = adjust_merged_sheeting_df(merged_sheeting_df)

# Common columns to select
common_columns = ['First Name', 'Last Name', 'Start Date', 'Employee Number',
                  'Working Hours', 'Process', 'MakeReady', 'Number of Lines', 'Output Qty',
                  'Revenue', 'Location', 'Machine', 'Silver Rate', 'Gold Rate',
                  'flag_not_report_working_hour', 'Silver', 'Gold', 'Silver Bonus', 'Gold Bonus']

# Concatenating the two DataFrames
merged_df = concatenate_dataframes(merged_sheeting_df, merged_other_df, common_columns)

# Generating reports
bonus_report = generate_bonus_report(merged_df)
not_reported_working_hour_report = generate_not_reported_working_hour_report(merged_df)
print("\n2.3 eports generated.")

# 3. Export to Excel
filename = save_reports_to_excel(merged_df, bonus_report, not_reported_working_hour_report, input_directory)
print("\n3. Reports saved to Excel.")

# 4. Analysis Merged Data and Saved to PDF
# Save charts to PDF
yearmth = pd.to_datetime(merged_df['Start Date']).min().strftime('%b %Y')
pdf_path = f'{input_directory}/Performance Measurement Summary {yearmth}.pdf'

with PdfPages(pdf_path) as pdf:
    # Title page
    plt.figure(figsize=(12, 6))
    title = f"Performance Summary {yearmth}"
    plt.text(0.5, 0.6, title, fontsize=28, ha='center', va='center', fontweight='bold')
    plt.text(0.5, 0.4, 'Beneco', fontsize=20, ha='center', va='center')
    plt.axis('off')
    pdf.savefig()
    plt.close()
    
    # Working Hours by Process and Location
    working_hours_by_process_location = merged_df.groupby(['Process', 'Location'])['Working Hours'].sum().reset_index()
    create_bar_chart(working_hours_by_process_location, 'Process', 'Working Hours', 'Location', 'Working Hours by Process and Location', 'Process', 'Working Hours', pdf)
    
    # Makeready by Process and Location
    makeready_by_process_location = merged_df.groupby(['Process', 'Location'])['MakeReady'].sum().reset_index()
    create_bar_chart(makeready_by_process_location, 'Process', 'MakeReady', 'Location', 'Makeready by Process and Location', 'Process', 'Makeready', pdf)
    
    # Output Quantity by Process and Location
    output_qty_by_process_location = merged_df.groupby(['Process', 'Location'])['Output Qty'].sum().reset_index()
    create_bar_chart(output_qty_by_process_location, 'Process', 'Output Qty', 'Location', 'Output Quantity by Process and Location', 'Process', 'Output Qty', pdf)
    
    # Revenue by Process and Location
    revenue_by_process_location = merged_df.groupby(['Process', 'Location'])['Revenue'].sum().reset_index()
    create_bar_chart(revenue_by_process_location, 'Process', 'Revenue', 'Location', 'Revenue by Process and Location', 'Process', 'Revenue', pdf)
    
    # Working Hours by Employee and Process
    working_hours_by_employee_process = merged_df.groupby(['Employee Number', 'Process'])['Working Hours'].sum().reset_index()
    working_hours_by_employee_process = working_hours_by_employee_process[working_hours_by_employee_process['Working Hours'] >= 8]
    create_horizontal_bar_chart(working_hours_by_employee_process, 'Working Hours', 'Employee Number', 'Process', 'Working Hours by Employee and Process', 'Working Hours', 'Employee Number', pdf)

    # Makeready by Employee and Process
    makeready_by_employee_process = merged_df.groupby(['Employee Number', 'Process'])['MakeReady'].sum().reset_index()
    makeready_by_employee_process = makeready_by_employee_process[makeready_by_employee_process['MakeReady'] > 0]
    create_horizontal_bar_chart(makeready_by_employee_process, 'MakeReady', 'Employee Number', 'Process', 'Makeready by Employee and Process', 'Makeready', 'Employee Number', pdf)

    # Output Quantity by Employee and Process
    output_qty_by_employee_process = merged_df.groupby(['Employee Number', 'Process'])['Output Qty'].sum().reset_index()
    output_qty_by_employee_process = output_qty_by_employee_process[output_qty_by_employee_process['Output Qty'] > 100]
    create_horizontal_bar_chart(output_qty_by_employee_process, 'Output Qty', 'Employee Number', 'Process', 'Output Quantity by Employee and Process', 'Output Qty', 'Employee Number', pdf)

    # Revenue by Employee and Process
    revenue_by_employee_process = merged_df.groupby(['Employee Number', 'Process'])['Revenue'].sum().reset_index()
    revenue_by_employee_process = revenue_by_employee_process[revenue_by_employee_process['Revenue'] > 100]
    create_horizontal_bar_chart(revenue_by_employee_process, 'Revenue', 'Employee Number', 'Process', 'Revenue by Employee and Process', 'Revenue', 'Employee Number', pdf)

print("\n4. PDF saved.")
print("\nPipeline exited successfully")