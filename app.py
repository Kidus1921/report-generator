import os
from flask import Flask, request, render_template, redirect, url_for,jsonify, send_file, flash, send_from_directory
import pandas as pd
from io import BytesIO
from datetime import datetime
import glob



app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
RESULT_FOLDER = 'static/results'

# Ensure upload and processed folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)


app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER

# Define folders

RESULTS_FOLDER = 'static/results'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULTS_FOLDER'] = RESULTS_FOLDER

# Ensure results folder exists
os.makedirs(RESULTS_FOLDER, exist_ok=True)

def classify_items_and_doctors(item_file, doctor_list_file):
    # Load the Excel files
    items_df = pd.read_excel(item_file)
    doctor_list_df = pd.read_excel(doctor_list_file, header=0)

    # Reshape the doctor list into a long format
    doctor_department_mapping = doctor_list_df.melt(var_name='Department', value_name='Doctor').dropna()

    # Aggregate the item file by doctor name to sum their quantities
    items_df.columns = ['Doctor', 'Quantity']
    aggregated_items = items_df.groupby('Doctor', as_index=False)['Quantity'].sum()

    # Merge the aggregated quantities with the doctor-department mapping
    merged_df = pd.merge(doctor_department_mapping, aggregated_items, on='Doctor', how='inner')

    # Group by department to calculate the total quantity for each department
    department_summary = merged_df.groupby('Department', as_index=False)['Quantity'].sum()

    # Add a total row at the bottom of the department summary
    total_department = pd.DataFrame({'Department': ['Total'], 'Quantity': [department_summary['Quantity'].sum()]})
    department_summary = pd.concat([department_summary, total_department], ignore_index=True)

    # Generate timestamp for the filename
    date_str = datetime.now().strftime('%Y%m%d')

    # Define file paths in static/results/
    output_file = os.path.join(RESULTS_FOLDER, f'Classified_{date_str}.xlsx')
    remaining_items_file = os.path.join(RESULTS_FOLDER, f'Remaining_Items_{date_str}.xlsx')

    # Save the department summary to an output Excel file
    department_summary.to_excel(output_file, index=False)

    # Find the remaining items that couldn't be classified
    remaining_items = aggregated_items[~aggregated_items['Doctor'].isin(merged_df['Doctor'])]

    # Add a total row at the bottom of the remaining items
    total_remaining = pd.DataFrame({'Doctor': ['Total'], 'Quantity': [remaining_items['Quantity'].sum()]})
    remaining_items = pd.concat([remaining_items, total_remaining], ignore_index=True)

    # Save the remaining items to a separate Excel file
    remaining_items.to_excel(remaining_items_file, index=False)

    return output_file, remaining_items_file  # Return paths for further use

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Handle file uploads
        if 'item_file' not in request.files or 'doctor_list_file' not in request.files:
            flash('Please upload both files.', 'error')
            return redirect(request.url)

        item_file = request.files['item_file']
        doctor_list_file = request.files['doctor_list_file']

        if item_file.filename == '' or doctor_list_file.filename == '':
            flash('Both files must have valid names.', 'error')
            return redirect(request.url)

        item_path = os.path.join(UPLOAD_FOLDER, item_file.filename)
        doctor_list_path = os.path.join(UPLOAD_FOLDER, doctor_list_file.filename)

        # Save uploaded files
        item_file.save(item_path)
        doctor_list_file.save(doctor_list_path)

        # Perform classification
        classified_file, remaining_file = classify_items_and_doctors(item_path, doctor_list_path)

        flash(f'Files processed successfully! <a href="{url_for("static", filename=classified_file)}">Download Classified Report</a>', 'success')

        return redirect(url_for('results'))

    return render_template('index.html')
@app.route('/results')
def results():
    results_folder = os.path.join(app.static_folder, 'results')
    
    # List all files in the 'results' folder
    files = os.listdir(results_folder)
    
    # Sort files by date (modification time)
    files.sort(key=lambda f: os.path.getmtime(os.path.join(results_folder, f)), reverse=True)
    
    # Categorize files based on their names
    sales_summarized = [f for f in files if 'sales' in f.lower() and 'summarized' in f.lower()]
    sales_excluded = [f for f in files if 'sales' in f.lower() and 'excluded' in f.lower()]
    
    advance_summarized = [f for f in files if 'advance' in f.lower() and 'summarized' in f.lower()]
    advance_excluded = [f for f in files if 'advance' in f.lower() and 'excluded' in f.lower()]
    
    credit_summarized = [f for f in files if 'credit' in f.lower() and 'summarized' in f.lower()]
    credit_excluded = [f for f in files if 'credit' in f.lower() and 'excluded' in f.lower()]
    
    # Pass the categorized and sorted files to the results template
    return render_template('results.html',
                           sales_summarized=sales_summarized,
                           sales_excluded=sales_excluded,
                           advance_summarized=advance_summarized,
                           advance_excluded=advance_excluded,
                           credit_summarized=credit_summarized,
                           credit_excluded=credit_excluded)


@app.route('/download/<filename>')
def download_file(filename):
    file_path = os.path.join(app.config['PROCESSED_FOLDER'], filename)
    return send_file(file_path, as_attachment=True)

@app.route('/pharmacy_report', methods=['GET', 'POST'])
def pharmacy_report():
    results = {'sales': None, 'advance': None, 'credit': None}

    if request.method == 'POST':
        # Handle file uploads and selected file type
        file_type = request.form.get('file_type')
        if not file_type:
            flash('Please select a file type.', 'error')
            return redirect(request.url)

        if 'merged_file' not in request.files or 'exclude_file' not in request.files:
            flash('Please upload both files.', 'error')
            return redirect(request.url)

        merged_file = request.files['merged_file']
        exclude_file = request.files['exclude_file']

        if merged_file.filename == '' or exclude_file.filename == '':
            flash('Both files must have valid names.', 'error')
            return redirect(request.url)

        # Save uploaded files to the upload folder
        merged_file_path = os.path.join(UPLOAD_FOLDER, merged_file.filename)
        exclude_file_path = os.path.join(UPLOAD_FOLDER, exclude_file.filename)
        merged_file.save(merged_file_path)
        exclude_file.save(exclude_file_path)

        # File naming with type and date
        current_date = datetime.now().strftime('%Y-%m-%d')
        base_filename = f"{file_type}_{current_date}.xlsx"
        summarized_file_path = os.path.join(RESULT_FOLDER, f"Summarized_{base_filename}")
        excluded_file_path = os.path.join(RESULT_FOLDER, f"Excluded_{base_filename}")

        try:
            # Load the Excel files
            merged_df = pd.read_excel(merged_file_path)
            exclude_df = pd.read_excel(exclude_file_path)

            # Normalize column names
            merged_df.columns = merged_df.columns.str.strip().str.lower()
            exclude_df.columns = exclude_df.columns.str.strip().str.lower()

            # Ensure required columns exist
            required_columns = {'items', 'price', 'quantity'}
            if not required_columns.issubset(set(merged_df.columns)):
                missing = required_columns - set(merged_df.columns)
                flash(f"The merged file is missing the following columns: {', '.join(missing)}", 'error')
                return redirect(request.url)

            # Convert items to lowercase for consistency
            merged_df['items'] = merged_df['items'].str.lower()
            exclude_df['items'] = exclude_df['items'].str.lower()

            # Process data
            exclude_set = set(zip(exclude_df['items'], exclude_df['price']))
            excluded_df = merged_df[merged_df[['items', 'price']].apply(tuple, axis=1).isin(exclude_set)]
            remaining_df = merged_df[~merged_df[['items', 'price']].apply(tuple, axis=1).isin(exclude_set)]

            # Summarize remaining data
            summarized_df = remaining_df.groupby(['items', 'price'], as_index=False)['quantity'].sum()
            summarized_df['total'] = summarized_df['quantity'] * summarized_df['price']

            # Calculate grand total
            grand_total = summarized_df['total'].sum()

            # Append grand total to the Excel file
            with pd.ExcelWriter(summarized_file_path, engine='openpyxl') as writer:
                summarized_df.to_excel(writer, index=False, sheet_name='Summary')
                workbook = writer.book
                worksheet = writer.sheets['Summary']
                worksheet.append(['Grand Total', '', '', grand_total])

            # Handle excluded data
            if excluded_df.empty:
                # Write "No items are excluded" if excluded DataFrame is empty
                with pd.ExcelWriter(excluded_file_path, engine='openpyxl') as writer:
                    pd.DataFrame({'Message': ['No items are excluded']}).to_excel(writer, index=False, sheet_name='Excluded')
            else:
                excluded_df['total'] = excluded_df['quantity'] * excluded_df['price']
                excluded_df.to_excel(excluded_file_path, index=False)

            # Update results for the selected file type
            results[file_type.lower()] = {
                'summarized': url_for('static', filename=f"result/Summarized_{base_filename}"),
                'excluded': url_for('static', filename=f"result/Excluded_{base_filename}")
            }

            flash('Files processed successfully!', 'success')

        except Exception as e:
            flash(f"An error occurred: {e}", 'error')

    return render_template('pharmacy_report.html', results=results)
@app.route('/dashboard')
def dashboard():
    results_folder = os.path.join(app.static_folder, 'results')
    
    # List all files in the 'results' folder
    files = os.listdir(results_folder)
    
    # Sort files by date (modification time)
    files.sort(key=lambda f: os.path.getmtime(os.path.join(results_folder, f)), reverse=True)
    
    # Categorize files based on their names
    sales_summarized = [f for f in files if 'sales' in f.lower() and 'summarized' in f.lower()]
    sales_excluded = [f for f in files if 'sales' in f.lower() and 'excluded' in f.lower()]
    
    advance_summarized = [f for f in files if 'advance' in f.lower() and 'summarized' in f.lower()]
    advance_excluded = [f for f in files if 'advance' in f.lower() and 'excluded' in f.lower()]
    
    credit_summarized = [f for f in files if 'credit' in f.lower() and 'summarized' in f.lower()]
    credit_excluded = [f for f in files if 'credit' in f.lower() and 'excluded' in f.lower()]
    
    # Filter Credit_result files
    credit_results = [f for f in files if f.startswith('Credit_result')] 
    classified_files = [file for file in os.listdir(RESULTS_FOLDER) if file.startswith('Classified_') and file.endswith('.xlsx')]


    return render_template('dashboard.html',
                       sales_summarized=sales_summarized,
                       sales_excluded=sales_excluded,
                       advance_summarized=advance_summarized,
                       advance_excluded=advance_excluded,
                       credit_summarized=credit_summarized,
                       credit_excluded=credit_excluded,
                       credit_reports=credit_results,
                       classified_files=classified_files)  # Add credit_reports here


@app.route('/credit', methods=['POST'])
def credit():
    # Get folder path from the request JSON payload
    data = request.get_json()
    folder_path = data.get('folderPath')

    if not folder_path:
        return jsonify({"error": "No folder path provided"}), 400

    # Ensure folder path is valid
    if not os.path.isdir(folder_path):
        return jsonify({"error": "Invalid folder path"}), 400

    # Get the Excel files in the provided folder path
    file_paths = glob.glob(folder_path + "*.xlsx")

    if not file_paths:
        return jsonify({"error": "No Excel files found in the provided folder"}), 400

    # Initialize an empty DataFrame to store combined results
    combined_results = pd.DataFrame()
    output_file = 'C:/Users/Delt/Desktop/AllReports/weekly/combined_duplicated_items_count.xlsx'  # Replace with desired output file path

    # List to store individual file results
    file_results = []

    for file_path in file_paths:
        try:
            # Read each Excel file
            data = pd.read_excel(file_path)

            # Check if the required 'Item' column exists
            if 'Item' not in data.columns:
                return jsonify({"error": f"The 'Item' column is not found in the file: {file_path}"}), 400

            # Convert all items to lowercase
            data['Item'] = data['Item'].str.lower()

            # Count the occurrences of each item
            item_counts = data['Item'].value_counts()

            # Create a DataFrame to display the counts
            result = pd.DataFrame({'Item': item_counts.index, 'Count': item_counts.values})

            # Add total row for individual file
            total_row = pd.DataFrame({'Item': ['Total'], 'Count': [result['Count'].sum()]})
            result_with_total = pd.concat([result, total_row], ignore_index=True)

            # Add file result to list (for writing to individual sheets)
            file_results.append((file_path, result_with_total))

            # Append only the item counts (excluding 'Total') to the combined DataFrame
            combined_results = pd.concat([combined_results, result], ignore_index=True)

        except Exception as e:
            return jsonify({"error": f"Error processing file {file_path}: {e}"}), 500

    # Aggregate the combined results
    final_counts = combined_results.groupby('Item', as_index=False).sum()

    # Add a total row at the bottom for combined results
    total_count = final_counts['Count'].sum()
    final_counts = pd.concat([final_counts, pd.DataFrame({'Item': ['Total'], 'Count': [total_count]})], ignore_index=True)

    # Save all results to a single Excel file
    try:
        with pd.ExcelWriter(output_file) as writer:
            # Write individual file results
            for i, (file_path, result_with_total) in enumerate(file_results):
                # Extract the file name without extension
                sheet_name = os.path.splitext(os.path.basename(file_path))[0]  # Get file name without extension
                result_with_total.to_excel(writer, sheet_name=sheet_name, index=False)

            # Write combined results
            final_counts.to_excel(writer, sheet_name="Combined", index=False)

        return jsonify({"message": f"All results have been saved to {output_file}."})

    except Exception as e:
        return jsonify({"error": f"Error saving the results: {e}"}), 500



# Route for credits page
@app.route('/credits')
def credits():
    return render_template('credits.html')

# Route to handle file processing
@app.route('/process_files', methods=['POST'])
def process_files():
    # Get the uploaded folder path from the form
    folder_path = request.form.get('folder_path')  # Get folder path from form

    if not folder_path:
        return "Folder path is required", 400

    file_paths = glob.glob(os.path.join(folder_path, "*.xlsx"))

    if not file_paths:
        return "No Excel files found in the provided folder.", 400

    # Initialize an empty DataFrame to store combined results
    combined_results = pd.DataFrame()

    # Get current date in YYYYMMDD format
    current_date = datetime.now().strftime('%Y%m%d')

    # Define output file name with current date
    output_file = os.path.join('static', 'results', f'Credit_result_{current_date}.xlsx')

    # List to store individual file results
    file_results = []

    for file_path in file_paths:
        try:
            # Read each Excel file
            data = pd.read_excel(file_path)

            # Log columns in the file for debugging
            print(f"Processing file: {file_path}")
            print(f"Columns in the file: {data.columns.tolist()}")

            # Check if the required 'Item' column exists
            if 'Item' not in data.columns:
                print(f"The 'Item' column is not found in the file: {file_path}")
                continue

            # Strip extra spaces and convert all items to lowercase
            data['Item'] = data['Item'].str.strip().str.lower()

            # Count the occurrences of each item
            item_counts = data['Item'].value_counts()

            # Create a DataFrame to display the counts
            result = pd.DataFrame({'Item': item_counts.index, 'Count': item_counts.values})

            # Add total row for individual file
            total_row = pd.DataFrame({'Item': ['Total'], 'Count': [result['Count'].sum()]})
            result_with_total = pd.concat([result, total_row], ignore_index=True)

            # Add file result to list (for writing to individual sheets)
            file_results.append((file_path, result_with_total))

            # Append only the item counts (excluding 'Total') to the combined DataFrame
            combined_results = pd.concat([combined_results, result], ignore_index=True)

        except Exception as e:
            print(f"Error processing file {file_path}: {e}")

    # Check if combined_results has data
    if combined_results.empty:
        return "No valid 'Item' data found in the files provided.", 400

    # Aggregate the combined results
    final_counts = combined_results.groupby('Item', as_index=False).sum()

    # Add a total row at the bottom for combined results
    total_count = final_counts['Count'].sum()
    final_counts = pd.concat([final_counts, pd.DataFrame({'Item': ['Total'], 'Count': [total_count]})], ignore_index=True)

    # Save all results to a single Excel file in static/results
    if not os.path.exists('static/results'):
        os.makedirs('static/results')  # Ensure the output directory exists

    with pd.ExcelWriter(output_file) as writer:
        # Write individual file results
        for file_path, result_with_total in file_results:
            # Extract the file name without extension
            sheet_name = os.path.splitext(os.path.basename(file_path))[0]  # Get file name without extension
            result_with_total.to_excel(writer, sheet_name=sheet_name, index=False)

        # Write combined results
        final_counts.to_excel(writer, sheet_name="Combined", index=False)

    return f"All results have been saved to {output_file}.", 200

if __name__ == '__main__':
    app.run(debug=True)
