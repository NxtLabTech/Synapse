from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.cloner import GitManager 
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Enable CORS so your frontend can talk to your backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 1. Define what the request body should look like
class RepoRequest(BaseModel):
    url: str

# 2. Create the Endpoint
@app.post("/clone")
async def clone_repository(request: RepoRequest):
    path = "./cloned_repo"
    repo_cloner = gitmanager(request.url, path)
    
    is_repo_cloned = repo_cloner.clone_repo()
    
    if is_repo_cloned:
        return {"message": "Successfully cloned the repository."}
    else:
        # We send a 400 error so the frontend knows it failed
        raise HTTPException(status_code=400, detail="Cloning failed. Please check the URL.")

# To run this, you will use: uvicorn main:app --reload