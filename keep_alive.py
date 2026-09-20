from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running 24/7! 🚀"

def run():
    app.run(host='0.0.0.0', port=7860)

def keep_alive():
    server = Thread(target=run)
    server.start()