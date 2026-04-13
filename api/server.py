from fastapi import FastAPI
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.routes import router

app = FastAPI(title="Player Clustering API", version="0.1.0")
app.include_router(router)
