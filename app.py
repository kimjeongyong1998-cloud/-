import os, sqlite3, uuid
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
import torch
import torch.nn.functional as F
from transformers import AutoImageProcessor, AutoModel

BASE=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(BASE,"data.db")
UPLOAD=os.path.join(BASE,"static","uploads")
os.makedirs(UPLOAD,exist_ok=True)

app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","CHANGE_ME")
app.config["MAX_CONTENT_LENGTH"]=10*1024*1024
ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD","CHANGE_ME")

MODEL_NAME="facebook/dinov2-small"
processor=None
model=None

def get_model():
    global processor,model
    if model is None:
        processor=AutoImageProcessor.from_pretrained(MODEL_NAME)
        model=AutoModel.from_pretrained(MODEL_NAME)
        model.eval()
    return processor,model

def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    c=conn()
    c.execute("""CREATE TABLE IF NOT EXISTS settings(
      id INTEGER PRIMARY KEY CHECK(id=1),
      reference_image TEXT,
      reference_embedding TEXT,
      threshold REAL DEFAULT 80
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS checks(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      filename TEXT, score REAL, result TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("INSERT OR IGNORE INTO settings(id,threshold) VALUES(1,80)")
    c.commit(); c.close()

def admin_required(f):
    @wraps(f)
    def w(*a,**kw):
        if not session.get("admin"): return redirect(url_for("login"))
        return f(*a,**kw)
    return w

def save_upload(file):
    if not file or not file.filename: raise ValueError("사진을 선택해주세요.")
    ext=os.path.splitext(secure_filename(file.filename))[1].lower()
    if ext not in [".jpg",".jpeg",".png",".webp"]: raise ValueError("JPG, PNG, WEBP만 가능합니다.")
    name=uuid.uuid4().hex+ext
    path=os.path.join(UPLOAD,name); file.save(path)
    return name,path

@torch.inference_mode()
def embedding(path):
    p,m=get_model()
    image=Image.open(path).convert("RGB")
    inputs=p(images=image,return_tensors="pt")
    outputs=m(**inputs)
    # CLS token as global image representation
    emb=outputs.last_hidden_state[:,0,:]
    emb=F.normalize(emb,p=2,dim=1)
    return emb[0].cpu()

def embedding_from_list(s):
    return torch.tensor([float(x) for x in s.split(",")])

@app.route("/")
def home(): return redirect(url_for("participant"))

@app.route("/admin/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        if request.form.get("password")==ADMIN_PASSWORD:
            session["admin"]=True; return redirect(url_for("admin"))
        flash("비밀번호가 틀렸습니다.")
    return render_template("login.html")

@app.route("/admin/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.route("/admin")
@admin_required
def admin():
    c=conn(); s=c.execute("SELECT * FROM settings WHERE id=1").fetchone()
    checks=c.execute("SELECT * FROM checks ORDER BY id DESC LIMIT 100").fetchall()
    c.close()
    return render_template("admin.html",s=s,checks=checks)

@app.route("/admin/reference",methods=["POST"])
@admin_required
def reference():
    try:
        name,path=save_upload(request.files.get("reference"))
        emb=embedding(path)
        value=",".join(str(float(x)) for x in emb)
        c=conn()
        old=c.execute("SELECT reference_image FROM settings WHERE id=1").fetchone()["reference_image"]
        c.execute("UPDATE settings SET reference_image=?,reference_embedding=? WHERE id=1",(name,value))
        c.commit(); c.close()
        if old:
            oldp=os.path.join(UPLOAD,old)
            if os.path.exists(oldp): os.remove(oldp)
        flash("기준 사진과 AI 특징값을 저장했습니다.")
    except Exception as e: flash(str(e))
    return redirect(url_for("admin"))

@app.route("/admin/threshold",methods=["POST"])
@admin_required
def set_threshold():
    try:
        x=max(0,min(100,float(request.form["threshold"])))
        c=conn(); c.execute("UPDATE settings SET threshold=? WHERE id=1",(x,)); c.commit(); c.close()
        flash("PASS 기준을 저장했습니다.")
    except Exception as e: flash(str(e))
    return redirect(url_for("admin"))

@app.route("/participant")
def participant():
    s=conn().execute("SELECT * FROM settings WHERE id=1").fetchone()
    return render_template("participant.html",ready=bool(s["reference_embedding"]))

@app.route("/api/check",methods=["POST"])
def check():
    try:
        c=conn(); s=c.execute("SELECT * FROM settings WHERE id=1").fetchone(); c.close()
        if not s["reference_embedding"]: return jsonify(ok=False,error="관리자가 아직 기준 사진을 설정하지 않았습니다."),400
        name,path=save_upload(request.files.get("photo"))
        ref=embedding_from_list(s["reference_embedding"])
        test=embedding(path)
        cosine=float(F.cosine_similarity(ref.unsqueeze(0),test.unsqueeze(0)).item())
        # Convert cosine similarity [-1,1] to a 0-100 score.
        score=max(0,min(100,(cosine+1)*50))
        passed=score>=float(s["threshold"])
        c=conn(); c.execute("INSERT INTO checks(filename,score,result) VALUES(?,?,?)",(name,round(score,2),"PASS" if passed else "FAIL")); c.commit(); c.close()
        # Uploaded participant image is not displayed publicly after the result.
        try: os.remove(path)
        except: pass
        return jsonify(ok=True,score=round(score,2),threshold=float(s["threshold"]),result="PASS" if passed else "FAIL")
    except Exception as e:
        return jsonify(ok=False,error=str(e)),400

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
