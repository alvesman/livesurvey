from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import timedelta
import sqlite3
import random
import time
import os

import yaml

app = Flask(__name__)
app.secret_key = '_! SecretKey !_'

# Retrieve the session lifetime from an environment variable or use a default value (in minutes)
session_lifetime_minutes = int(os.environ.get('PERMANENT_SESSION_LIFETIME', 10))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=session_lifetime_minutes)

# Database file
DATABASE = './questions_bank/survey.db'


# Helper function to get a database connection
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # This enables name-based access to columns
    # Enable Write-Ahead Logging (WAL) mode. In WAL mode, reads and writes 
    # can occur at the same time without blocking each other as much as in the default DELETE mode.
    conn.execute('PRAGMA journal_mode = WAL;')
    return conn


# Function to initialize the database (if not already present)
def init_db():
    with get_db_connection() as conn:
        # Create table if not exists
        conn.execute('''CREATE TABLE IF NOT EXISTS questions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            question TEXT NOT NULL,
                            options TEXT NOT NULL,
                            votes TEXT NOT NULL,
                            PIN TEXT NOT NULL UNIQUE
                        )''')
        conn.commit()

        # Check if the table is empty and seed with initial data
        result = conn.execute('SELECT COUNT(*) as count FROM questions').fetchone()
        if result['count'] == 0:
            # Default question and options
            question = "What's your favorite programming paradigm?"
            options = ['Imperative, like C', 'Functional, like Haskell', 'Other']
            votes = [0] * len(options)  # Initialize votes to 0 for each option
            pin = '0'  # Default PIN for this initial question

            # Insert default question into the table
            conn.execute(
                'INSERT INTO questions (question, options, votes, PIN) VALUES (?, ?, ?, ?)',
                (question, '§'.join(options), ','.join(map(str, votes)), pin)
            )
            conn.commit()
            print("Database seeded with default question and options.")


# Function to load data from the database with concurrency support and retry mechanism
def load_data():
    pin = session.get('pin')
    if not pin:
        return {}

    max_retries = 10  # Maximum number of retries for handling database locks

    for attempt in range(max_retries):
        try:
            with get_db_connection() as conn:
                data = conn.execute('SELECT * FROM questions WHERE PIN = ?', (pin,)).fetchone()
                if data:
                    options = data['options'].split('§')
                    votes = {option: int(vote) for option, vote in zip(options, data['votes'].split(','))}
                    return {
                        'question': data['question'],
                        'options': options,
                        'votes': votes,
                        'PIN': data['PIN']
                    }
                else:
                    return {}
        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e):
                retry_delay = random.uniform(0.1, 0.2)  # Random delay between 0.1 and 0.2 seconds
                print(f"Database is locked. Retrying {attempt + 1}/{max_retries} after {retry_delay:.2f} seconds...")
                time.sleep(retry_delay)
            else:
                raise  # Raise other database-related errors
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            raise
    else:
        # If all retries fail, raise an exception
        raise Exception("Failed to load data after multiple retries due to database locking issues.")


# Function to save data to the database with concurrency support and randomized retry delay
def save_data(data):
    max_retries = 10  # Maximum number of retries for handling database locks

    for attempt in range(max_retries):
        try:
            with get_db_connection() as conn:
                # Convert the votes dictionary to a comma-separated string
                votes = ','.join(str(data['votes'][option]) for option in data['options'])
                # Update the database with the new data
                conn.execute(
                    'UPDATE questions SET question = ?, options = ?, votes = ? WHERE PIN = ?',
                    (data['question'], '§'.join(data['options']), votes, data['PIN'])
                )
                conn.commit()
                break  # Exit the retry loop if the operation succeeds
        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e):
                # If the database is locked, wait and retry
                retry_delay = random.uniform(0.1, 0.9)  # Random delay between 0.1 and 0.9 seconds
                print(f"Database is locked. Retrying {attempt + 1}/{max_retries} after {retry_delay:.2f} seconds...")
                time.sleep(retry_delay)
            else:
                # If any other database error occurs, re-raise the exception
                raise
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            raise
    else:
        # If all retries fail, raise an exception
        raise Exception("Failed to save data after multiple retries due to database locking issues.")

@app.route('/reset', methods=['GET', 'POST'])
def reset():
    with get_db_connection() as conn:
        # Retrieve all the questions from the database
        questions = conn.execute('SELECT * FROM questions').fetchall()
        
        # Loop through each question and reset the votes to zero for each option
        for question in questions:
            options = question['options'].split('§')
            zeroed_votes = ','.join(['0'] * len(options))  # Create a zeroed votes string for all options
            # Update the votes column for the question
            conn.execute('UPDATE questions SET votes = ? WHERE id = ?', (zeroed_votes, question['id']))
        
        conn.commit()  # Commit the changes to the database
    flash("All votes have been reset!")
    return redirect(url_for('enter_pin'))


@app.route('/show', methods=['GET', 'POST'])
def show():
    data = load_data()
    total_votes = sum(data['votes'].values())  # Calculate the total votes
    return render_template('showvotes.html', question=data['question'], options=data['options'], votes=data['votes'], total_votes=total_votes)


@app.route('/enter_pin', methods=['GET', 'POST'])
def enter_pin():
    if request.method == 'POST':
        entered_pin = request.form['pin']
        with get_db_connection() as conn:
            data = conn.execute('SELECT * FROM questions WHERE PIN = ?', (entered_pin,)).fetchone()
            if data:
                session['pin'] = entered_pin
                session['authenticated'] = True
                return redirect(url_for('vote'))
            else:
                flash('Incorrect PIN. Please try again.', 'danger')
    return render_template('enter_pin.html')


@app.route('/', methods=['GET', 'POST'])
def vote():
    if not session.get('authenticated'):
        return redirect(url_for('enter_pin'))

    data = load_data()

    # Check if the user has already voted
    if session.get('voted' + str(data['PIN'])):
        return render_template('already_voted.html', question=data['question'], options=data['options'], votes=data['votes'])

    if request.method == 'POST':
        selected_option = request.form['option']
        if selected_option in data['options']:
            data['votes'][selected_option] += 1
            save_data(data)

            session.permanent = True
            session['voted' + str(data['PIN'])] = True  # Mark the user as having voted

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
        question = request.form['question']
        options = request.form.getlist('options')
        votes = {option: 0 for option in options}
   
        data['question'] = question
        data['options'] = options
        data['votes'] = votes
        
        pin = request.form.get('pin')
        if pin:
            data['PIN'] = str(pin)
        save_data(data)
        flash('Data updated successfully!')
        return redirect(url_for('vote'))
    return render_template('update.html', data=data)

@app.route('/update_yaml', methods=['GET', 'POST'])
def update_yaml():
    if request.method == 'POST':
        yaml_text = request.form['yaml_data']
        try:
            # Parse the YAML data
            new_data = yaml.safe_load(yaml_text)
            
            # Validate that the necessary fields are present in the YAML structure
            if 'PIN' in new_data and 'question' in new_data and 'options' in new_data:
                pin = str(new_data['PIN'])
                question = new_data['question']
                options = new_data['options']
                
                # Initialize votes for each option to zero
                votes = [0] * len(options)
                
                with get_db_connection() as conn:
                    # Check if a question with this PIN already exists
                    existing_question = conn.execute('SELECT * FROM questions WHERE PIN = ?', (pin,)).fetchone()
                    
                    if existing_question:
                        # Update the existing question
                        conn.execute('UPDATE questions SET question = ?, options = ?, votes = ? WHERE PIN = ?',
                                     (question, ','.join(options), ','.join(map(str, votes)), pin))
                        flash('Question updated successfully!', 'success')
                    else:
                        # Insert a new question
                        conn.execute('INSERT INTO questions (question, options, votes, PIN) VALUES (?, ?, ?, ?)',
                                     (question, '§'.join(options), ','.join(map(str, votes)), pin))
                        flash('New question created successfully!', 'success')
                    
                    conn.commit()
                return redirect(url_for('vote'))
            else:
                flash('Invalid YAML structure. Please include "PIN", "question", and "options".', 'danger')
        except yaml.YAMLError as e:
            flash(f'Error parsing YAML: {e}', 'danger')
        except Exception as e:
            flash(f'An error occurred: {e}', 'danger')
    
    # Load current YAML data (for display purposes)
    data = load_data()
    if data:
        current_yaml = yaml.dump(data, default_flow_style=False)
    else:
        current_yaml = ''
    
    return render_template('update_yaml.html', current_yaml=current_yaml)


if __name__ == '__main__':
    # Initialize the database before running the app
    init_db()
    app.run(debug=False)

