from flask import Flask
from flask_pymongo import PyMongo
import os

app = Flask(__name__)
app.config['MONGO_URI'] = os.environ.get('MONGO_URI', None)
app.config['MONGO_CONNECT'] = False
app.config['MONGO_MAX_POOL_SIZE'] = None
mongo = PyMongo(app)

from app import routes
