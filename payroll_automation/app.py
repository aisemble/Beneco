import streamlit as st
from data_loading import load_timesheets, load_schedules, load_public_holidays, load_production_report, load_payrate_list
from salary_calculation import process_data
from report_generator import generate_excel_report
import os

# Directory for storing temp files (optional)
if not os.path.exists('temp'):
    os.makedirs('temp')

st.title("Payroll Automation Tool")

# File uploads
timesheet_file = st.file_uploader("Upload Timesheet Excel", type=["xlsx"])
schedule_file = st.file_uploader("Upload Schedule Excel", type=["xlsx"])
payrate_file = st.file_uploader("Upload Payrate Excel", type=["xlsx"])
public_holidays_file = st.file_uploader("Upload Public Holidays Excel", type=["xlsx"])
production_report_file = st.file_uploader("Upload Production Report Excel", type=["xlsx"])
start_date = st.date_input("Select Start Date")

if st.button("Process Payroll"):
    if all([timesheet_file, schedule_file, payrate_file, public_holidays_file, production_report_file]):
        # Save uploaded files
        timesheet_path = f"temp/{timesheet_file.name}"
        schedule_path = f"temp/{schedule_file.name}"
        payrate_path = f"temp/{payrate_file.name}"
        holidays_path = f"temp/{public_holidays_file.name}"
        production_report_path = f"temp/{production_report_file.name}"

        with open(timesheet_path, 'wb') as f:
            f.write(timesheet_file.getbuffer())
        with open(schedule_path, 'wb') as f:
            f.write(schedule_file.getbuffer())
        with open(payrate_path, 'wb') as f:
            f.write(payrate_file.getbuffer())
        with open(holidays_path, 'wb') as f:
            f.write(public_holidays_file.getbuffer())
        with open(production_report_path, 'wb') as f:
            f.write(production_report_file.getbuffer())

        # Load data
        combined_timesheet = load_timesheets('temp/')
        combined_schedule = load_schedules('temp/')
        ca_holidays = load_public_holidays(start_date)
        production_report = load_production_report('temp/')
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
