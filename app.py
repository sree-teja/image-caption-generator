import os
from flask import Flask, request, jsonify, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from keras.applications import DenseNet201
from keras.preprocessing.image import img_to_array
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.sequence import pad_sequences
import pickle
from flask_cors import CORS

# Constants
IMAGE_SIZE = (224, 224)
MAX_LENGTH = 34
UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

# Initialize Flask app


app = Flask(__name__)
CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://user:password@ep-frosty-water-a5ialw90.us-east-2.aws.neon.tech/neondb?sslmode=require"
app.config["SECRET_KEY"] = "secret-key"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize database
db = SQLAlchemy(app)

# Database model for users with name, email, and password
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

# Initialize DenseNet201 model for image feature extraction
base_model = DenseNet201(weights='imagenet', include_top=False, pooling='avg')
feature_extractor = base_model.output

# Load the pre-trained caption model and tokenizer
caption_model = load_model('./saves/model (1).h5')

def load_tokenizer() -> pickle:
    with open('./saves/tokenizer.pickle', 'rb') as handle:
        tokenizer = pickle.load(handle)
    return tokenizer

tokenizer = load_tokenizer()

# Utility Functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_features_from_img(image, size=IMAGE_SIZE):
    image = image.resize(size)
    img_array = img_to_array(image) / 255.0
    img_array = img_array.reshape((1, *img_array.shape))
    features = feature_extractor.predict(img_array)
    return features

def idx_to_word(integer, tokenizer):
    for word, index in tokenizer.word_index.items():
        if index == integer:
            return word
    return None

def predict_caption(img_features, tokenizer, max_length=MAX_LENGTH):
    in_text = "startseq"
    for _ in range(max_length):
        sequence = tokenizer.texts_to_sequences([in_text])[0]
        sequence = pad_sequences([sequence], maxlen=max_length)
        y_pred = caption_model.predict([img_features, sequence], verbose=0)
        y_pred = np.argmax(y_pred)
        word = idx_to_word(y_pred, tokenizer)
        if word is None:
            break
        in_text += " " + word
        if word == "endseq":
            break
    return in_text

# Routes
@app.route("/")
def home():
    return "Welcome to the Image Captioning API"

@app.route("/predict", methods=["POST"])
def predict_from_image_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part in the form!"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected!"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)
        image = Image.open(file_path)
        img_features = load_features_from_img(image)
        caption = predict_caption(img_features, tokenizer)
        caption = caption.replace("startseq", "").replace("endseq", "").strip()
        return jsonify({"caption": caption, "image_path": filename})

    return jsonify({"error": "Invalid file format"}), 400

@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User with this email already exists"}), 400

    hashed_password = generate_password_hash(password)
    new_user = User(name=name, email=email, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "User created successfully"}), 201

@app.route("/signin", methods=["POST"])
def signin():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()
    if user and check_password_hash(user.password, password):
        session["email"] = user.email
        return jsonify({"message": "User signed in successfully"}), 200

    return jsonify({"error": "Invalid email or password"}), 400

@app.route("/signout", methods=["POST"])
def signout():
    session.pop("email", None)
    return jsonify({"message": "User signed out successfully"}), 200

if __name__ == "__main__":
    # Ensure the database schema is correct
    with app.app_context():
        db.create_all()
    app.run(debug=True)
