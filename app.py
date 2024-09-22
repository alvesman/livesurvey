from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import timedelta
import yaml
import os

app = Flask(__name__)
app.secret_key = '_! SecretKey !_'

# Retrieve the session lifetime from an environment variable or use a default value (in minutes)
session_lifetime_minutes = int(os.environ.get('PERMANENT_SESSION_LIFETIME', 10))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=session_lifetime_minutes)

# Path to the YAML file
DATA_FILE = ''

# Function to load data from YAML
def load_data():
    global DATA_FILE
    data_file = "/questions_bank/" + DATA_FILE
    if os.path.exists(data_file):
        with open(data_file, 'r') as file:
            data = yaml.safe_load(file) or {}
    else:
        data = {}
        # Ensure default structure
        data.setdefault('question', "What's your favorite programming language?")
        data.setdefault('options', ['Python', 'JavaScript', 'Java', 'C', 'C++', 'Rust', 'C#', 'Ruby', 'Other'])
        data.setdefault('votes', {option: 0 for option in data['options']})
        data.setdefault('PIN', '1234')  # Default PIN as a string
    return data

# Function to save data to YAML
def save_data(data):
    global DATA_FILE
    data_file = "/questions_bank/" + DATA_FILE
    with open(data_file, 'w') as file:
        yaml.dump(data, file)

import os
import yaml
from flask import redirect, url_for, flash

@app.route('/reset', methods=['GET', 'POST'])
def reset():
    global DATA_FILE
    try:
        # read all file names from directory "/questions_bank/" 
        files = os.listdir("/questions_bank/")
        
        # for each file, read the data and reset the votes
        for file in files:
            data_file = file
            try:
                with open("/questions_bank/" + data_file, 'r') as file:
                    data = yaml.safe_load(file) or {}
                
                data['votes'] = {option: 0 for option in data['options']}
                
                with open("/questions_bank/" + data_file, 'w') as file:
                    yaml.dump(data, file)
            
            except FileNotFoundError:
                print(f"Error: {data_file} not found.")
                flash(f"Error: {data_file} not found.")
            except yaml.YAMLError as e:
                print(f"Error processing YAML file {data_file}: {e}")
                flash(f"Error processing YAML file {data_file}: {e}")
            except Exception as e:
                print(f"An error occurred while resetting {data_file}: {e}")
                flash(f"An error occurred while resetting {data_file}: {e}")
        
        # write to console
        print("All votes have been reset!")
        return redirect(url_for('enter_pin'))
    
    except FileNotFoundError:
        print("Error: The directory /questions_bank/ does not exist.")
        flash("Error: The directory /questions_bank/ does not exist.")
        return redirect(url_for('error'))
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        flash(f"An unexpected error occurred: {e}")
        return redirect(url_for('error'))

    
@app.route('/show', methods=['GET', 'POST'])
def show():
    data = load_data()
    total_votes = sum(data['votes'].values())  # Calculate the total votes
    return render_template('showvotes.html', question=data['question'], options=data['options'], votes=data['votes'], total_votes=total_votes)

@app.route('/enter_pin', methods=['GET', 'POST'])
def enter_pin():
    global DATA_FILE
    # data = load_data()
    if request.method == 'POST':
        entered_pin = request.form['pin']
        DATA_FILE = entered_pin + '.yaml'
        # data = load_data()
        session['authenticated'] = True
        return redirect(url_for('vote'))
        # if entered_pin == str(data['PIN']):
        #     session['authenticated'] = True
        #     # session['voted'] = False  # Reset the voted flag
        #     return redirect(url_for('vote'))
        # else:
        #     flash('Incorrect PIN. Please try again.', 'danger')
    return render_template('enter_pin.html')

@app.route('/', methods=['GET', 'POST'])
def vote():
    if not session.get('authenticated'):
        return redirect(url_for('enter_pin'))
    
    data = load_data()
    
    # Check if the user has already voted
    if session.get('voted'+str(data['PIN'])):
        # flash('You have already voted. You cannot vote again.', 'warning')
        # Pass the data to the already_voted template
        return render_template('already_voted.html', question=data['question'], options=data['options'], votes=data['votes'])

    if request.method == 'POST':
        selected_option = request.form['option']
        if selected_option in data['options']:
            data['votes'][selected_option] += 1
            save_data(data)
            
            session.permanent = True
            session['voted'+str(data['PIN'])] = True  # Mark the user as having voted
            
            flash('Thank you for voting!', 'success')
        return redirect(url_for('vote'))
    
    return render_template('vote.html', question=data['question'], options=data['options'], votes=data['votes'])


@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    session.pop('voted', None)  # Clear the voted flag on logout
    flash('You have been logged out.', 'info')
    return redirect(url_for('enter_pin'))

@app.route('/update', methods=['GET', 'POST'])
def update_data():
    data = load_data()
    if request.method == 'POST':
        # Get updated data from the form
        question = request.form['question']
        options = request.form.getlist('options')
        # Initialize votes for new options
        votes = {option: data['votes'].get(option, 0) for option in options}
        # Update the data
        data['question'] = question
        data['options'] = options
        data['votes'] = votes
        # Update the PIN if provided
        pin = request.form.get('pin')
        if pin:
            data['PIN'] = str(pin)
        save_data(data)
        flash('Data updated successfully!')
        return redirect(url_for('vote'))
    return render_template('update.html', data=data)

@app.route('/update_yaml', methods=['GET', 'POST'])
def update_yaml():
    data = load_data()
    if request.method == 'POST':
        yaml_text = request.form['yaml_data']
        try:
            new_data = yaml.safe_load(yaml_text)
            # Validate new_data structure
            if 'question' in new_data and 'options' in new_data and 'votes' in new_data and 'PIN' in new_data:
                data = new_data
                save_data(data)
                flash('YAML data updated successfully!', 'success')
                return redirect(url_for('vote'))
            else:
                flash('Invalid YAML structure. Please include "question", "options", "votes", and "PIN".', 'danger')
        except yaml.YAMLError as e:
            flash(f'Error parsing YAML: {e}', 'danger')
    # Load current YAML data to display in textarea
    global DATA_FILE
    data_file = "/questions_bank/" + DATA_FILE
    with open(data_file, 'r') as file:
        current_yaml = file.read()
    return render_template('update_yaml.html', current_yaml=current_yaml)

if __name__ == '__main__':
    app.run(debug=False)
