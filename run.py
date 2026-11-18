from app import create_app
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)