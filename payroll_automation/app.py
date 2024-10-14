import streamlit as st
from data_loading import load_timesheets, load_schedules, load_public_holidays, load_production_report, load_payrate_list
from salary_calculation import process_data
from report_generator import generate_excel_report
import os
import pandas as pd

# Directory for storing temp files (optional)
if not os.path.exists('temp'):
    os.makedirs('temp')

st.title("Payroll Automation Tool")

# Multi-file uploads for timesheet and schedule
timesheet_files = st.file_uploader("Upload Timesheet Excel Files", type=["xlsx"], accept_multiple_files=True)
schedule_files = st.file_uploader("Upload Schedule Excel Files", type=["xlsx"], accept_multiple_files=True)
payrate_file = st.file_uploader("Upload Payrate Excel", type=["xlsx"])
public_holidays_file = st.file_uploader("Upload Public Holidays Excel", type=["xlsx"], help="Optional")
production_report_file = st.file_uploader("Upload Production Report Excel", type=["xlsx"], help="Optional")
start_date = st.date_input("Select Start Date")

if st.button("Process Payroll"):
    if all([timesheet_files, schedule_files, payrate_file]):
        # Read uploaded files into dataframes
        timesheet_dfs = [pd.read_excel(timesheet) for timesheet in timesheet_files]
        schedule_dfs = [pd.read_excel(schedule) for schedule in schedule_files]
        payrate_df = pd.read_excel(payrate_file)

        # Optional files
        holidays_df = pd.read_excel(public_holidays_file) if public_holidays_file else None
        production_report_df = pd.read_excel(production_report_file) if production_report_file else None

        # Combine dataframes if needed
        combined_timesheet = pd.concat(timesheet_dfs, ignore_index=True)
        combined_schedule = pd.concat(schedule_dfs, ignore_index=True)

        # Process data
        # Replace this with your actual processing logic
        salary_info, vacation_info, schedule_changes, schedule_alerts = process_data(
            combined_timesheet, combined_schedule, holidays_df, production_report_df, payrate_df, start_date
        )

        # Generate report
        output_file = f"Payroll_Report_{start_date}.xlsx"
        generate_excel_report(salary_info, combined_timesheet, vacation_info, output_file, schedule_alerts, output_file)

        # Provide download link
        with open(output_file, "rb") as f:
            st.download_button("Download Payroll Report", f, file_name=output_file)
    else:
        st.error("Please upload all required files.")
