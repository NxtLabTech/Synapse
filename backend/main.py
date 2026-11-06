from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.cloner import GitManager
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()

# Allow the CORS origin to be overridden at runtime (e.g. Docker Compose sets
# FRONTEND_ORIGIN=http://localhost:5173).  Falls back to both common local dev
# addresses so plain `uvicorn main:app --reload` still works out of the box.
_frontend_origin = os.environ.get("FRONTEND_ORIGIN", "").strip()
_allowed_origins = (
    [_frontend_origin]
    if _frontend_origin
    else ["http://localhost:5173", "http://127.0.0.1:5173"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
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
    repo_cloner = GitManager(request.url, path)

    result = repo_cloner.clone_repo()

    if result is True:
        return {"message": "Successfully cloned the repository."}
    else:
        # result is an error string when cloning failed
        detail = result if isinstance(result, str) else "Cloning failed. Please check the URL."
        raise HTTPException(status_code=400, detail=detail)

# To run: uvicorn main:app --reload