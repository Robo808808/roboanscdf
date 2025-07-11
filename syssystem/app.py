from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import subprocess
import json

app = FastAPI()

class DBARequest(BaseModel):
    dba_id: str
    roles: List[str] = []

def run_dba_script(action, dba_id, roles=None):
    cmd = ["./manage_dba_account.py", action, dba_id]
    if roles:
        cmd.append(",".join(roles))
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "Invalid script output")

@app.post("/create")
def create_user(data: DBARequest):
    return run_dba_script("create", data.dba_id, data.roles)

@app.post("/modify")
def modify_user(data: DBARequest):
    return run_dba_script("modify", data.dba_id, data.roles)

@app.post("/delete")
def delete_user(data: DBARequest):
    return run_dba_script("delete", data.dba_id)

