import streamlit as st
from data_loading import read_excel_safe,load_timesheets,load_schedules,load_public_holidays,load_production_report,load_payrate_list
from schedule_processing import process_timesheet, process_temp_timesheet, process_schedule
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
        # Save uploaded files
        timesheet_paths = []
        schedule_paths = []
        
        # Save each uploaded timesheet file temporarily
        for timesheet in timesheet_files:
            temp_path = f"temp/{timesheet.name}"
            with open(temp_path, 'wb') as f:
                f.write(timesheet.getbuffer())
            timesheet_paths.append(temp_path)
        
        # Save each uploaded schedule file temporarily
        for schedule in schedule_files:
            temp_path = f"temp/{schedule.name}"
            with open(temp_path, 'wb') as f:
                f.write(schedule.getbuffer())
            schedule_paths.append(temp_path)

        payrate_path = f"temp/{payrate_file.name}"
        with open(payrate_path, 'wb') as f:
            f.write(payrate_file.getbuffer())
        
        # Optional files
        holidays_path = None
        if public_holidays_file:
            holidays_path = f"temp/{public_holidays_file.name}"
            with open(holidays_path, 'wb') as f:
                f.write(public_holidays_file.getbuffer())
        
        production_report_path = None
        if production_report_file:
            production_report_path = f"temp/{production_report_file.name}"
            with open(production_report_path, 'wb') as f:
                f.write(production_report_file.getbuffer())

        # Load data
        combined_timesheet = load_timesheets(timesheet_paths)
        combined_schedule = load_schedules(schedule_paths)
        ca_holidays = load_public_holidays(start_date)
        production_report = load_production_report(production_report_path)
        payrate_list = load_payrate_list(payrate_path)

        # Process data
        salary_info, vacation_info, schedule_changes, schedule_alerts = process_data(
            combined_timesheet, combined_schedule, ca_holidays, production_report, payrate_list, start_date
        )

        # Generate report
        output_file = f"Payroll_Report_{start_date}.xlsx"
        generate_excel_report(salary_info, combined_timesheet, vacation_info, output_file, schedule_alerts, output_file)

        # Provide download link
        with open(output_file, "rb") as f:
            st.download_button("Download Payroll Report", f, file_name=output_file)
    else:
        st.error("Please upload all required files.")
