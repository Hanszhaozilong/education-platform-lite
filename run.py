from dotenv import load_dotenv

load_dotenv()

from lite import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5003, debug=False)
