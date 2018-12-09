from app import app
from flask import render_template, request, redirect
from app.my_lib import chatbot_answers

@app.route('/')
@app.route('/index')
def index():
    return render_template("index.html")

@app.route('/query', methods=['POST'])
def query():
    raw_question = request.form['question']
    return chatbot_answers(raw_question)
