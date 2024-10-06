# Payroll Automation Tool

## Overview
This project automates payroll processing by reading multiple Excel files, performing calculations, and generating an Excel report with various tabs.

## How to Use

1. Clone the repository.
   ```bash
   git clone https://github.com/yourusername/payroll-automation.git
   cd payroll-automation

2. Install the required packages.
   pip install -r requirements.txt

3. Run the Streamlit app.
   pip install -r requirements.txt

4. Upload the required Excel files through the web interface and click "Process Payroll" to generate the report.

Project Structure

- data_loading.py: Contains functions for loading Excel files.
- schedule_processing.py: Functions for processing timesheets and schedules.
- time_adjustments.py: Functions for adjusting time records.
- salary_calculation.py: Salary calculation logic.
- report_generator.py: Report generation logic using OpenPyXL.
- app.py: Main script for running the app with Streamlit.